"""Rede elétrica FICTÍCIA sobre a base real do município configurado.

- Transformadores: agrupamento dos endereços reais (CNEFE) próximos entre si.
- Rede de média tensão: árvore de caminhos mínimos, pelas vias reais do OSM, da
  subestação até cada transformador.
- Alimentadores: subárvores com carga limitada.
- Chaves: início dos ramais. Abrir uma chave desliga tudo o que está a jusante.
"""

import math
import warnings

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString, Point
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.exceptions import ConvergenceWarning

from .. import config as C
from ..fontes import osm

# Transformadores
RAIO_TRAFO_RURAL_M = 450   # diâmetro máximo de um grupo de UCs rurais num mesmo trafo
MAX_UC_TRAFO_RURAL = 12
UC_POR_TRAFO_URBANO = 35
# Alimentadores e chaves
MAX_UC_ALIMENTADOR = 4500
MIN_UC_CHAVE = 8
MAX_UC_CHAVE = 1500


def _dividir(xy: np.ndarray, maximo: int, semente: int) -> np.ndarray:
    """Divide pontos em grupos de no máximo `maximo` (k-means aplicado recursivamente)."""
    rotulo = np.zeros(len(xy), dtype=int)
    if len(xy) <= maximo:
        return rotulo
    k = math.ceil(len(xy) / maximo)
    with warnings.catch_warnings():  # pontos coincidentes são tratados logo abaixo
        warnings.simplefilter("ignore", ConvergenceWarning)
        sub = KMeans(n_clusters=k, n_init=4, random_state=semente).fit_predict(xy)
    if len(np.unique(sub)) == 1:  # pontos coincidentes (ex.: prédio): divide em blocos
        return np.arange(len(xy)) // maximo
    prox = 0
    for s in np.unique(sub):
        m = np.where(sub == s)[0]
        r = _dividir(xy[m], maximo, semente)
        rotulo[m] = r + prox
        prox += r.max() + 1
    return rotulo


def transformadores(uc: gpd.GeoDataFrame) -> np.ndarray:
    """Retorna o índice do transformador de cada UC (agrupamento espacial)."""
    xy = np.c_[uc.geometry.x, uc.geometry.y]
    trafo = np.full(len(uc), -1)
    prox = 0
    rural = (uc["ZONA"] == "Rural").to_numpy()

    idx = np.where(rural)[0]
    grupos = AgglomerativeClustering(
        n_clusters=None, distance_threshold=RAIO_TRAFO_RURAL_M, linkage="complete"
    ).fit_predict(xy[idx])
    for gid in np.unique(grupos):
        membros = idx[grupos == gid]
        sub = _dividir(xy[membros], MAX_UC_TRAFO_RURAL, C.SEMENTE)
        for s in np.unique(sub):
            trafo[membros[sub == s]] = prox
            prox += 1

    # Urbano: por setor censitário, para não juntar quarteirões de bairros distantes
    for _, membros in uc[~rural].groupby("CD_SETOR").indices.items():
        membros = np.where(~rural)[0][membros]
        sub = _dividir(xy[membros], UC_POR_TRAFO_URBANO, C.SEMENTE)
        for s in np.unique(sub):
            trafo[membros[sub == s]] = prox
            prox += 1
    return trafo


def _arvore_mt(G: nx.Graph, raiz, alvos: set) -> nx.DiGraph:
    """Árvore de caminhos mínimos da raiz até os nós-alvo (só os trechos usados)."""
    _, caminhos = nx.single_source_dijkstra(G, raiz, weight="length")
    T = nx.DiGraph()
    T.add_node(raiz)
    for a in alvos:
        p = caminhos[a]
        nx.add_path(T, p)
    return T


def _alimentadores(T: nx.DiGraph, raiz, carga: dict, xy_no: dict) -> tuple:
    """Particiona a árvore em subárvores com carga <= MAX_UC_ALIMENTADOR. Retorna nó -> alimentador."""
    jusante = {}
    for n in reversed(list(nx.topological_sort(T))):
        jusante[n] = carga.get(n, 0) + sum(jusante[f] for f in T.successors(n))

    # 1) "Átomos": maiores subárvores com carga <= limite
    atomos = []

    def descer(n):
        for f in T.successors(n):
            if jusante[f] == 0:
                continue
            if jusante[f] > MAX_UC_ALIMENTADOR and list(T.successors(f)):
                descer(f)
            else:
                atomos.append(f)

    descer(raiz)

    # 2) Ordena os átomos pela direção (azimute) a partir da SE e empacota vizinhos
    x0, y0 = xy_no[raiz]

    def azimute(a):
        nos = list(nx.dfs_preorder_nodes(T, a))
        w = np.array([carga.get(n, 0) + 1e-9 for n in nos])
        p = np.array([xy_no[n] for n in nos])
        cx, cy = (p * w[:, None]).sum(0) / w.sum()
        return math.atan2(cy - y0, cx - x0)

    atomos.sort(key=azimute)
    grupos, pacote, soma = [], [], 0
    for a in atomos:
        if pacote and soma + jusante[a] > MAX_UC_ALIMENTADOR:
            grupos.append(pacote)
            pacote, soma = [], 0
        pacote.append(a)
        soma += jusante[a]
    grupos.append(pacote)
    grupos.sort(key=lambda g: -sum(jusante[a] for a in g))

    alim = {}
    for i, pacote in enumerate(grupos):
        for c in pacote:
            for n in nx.dfs_preorder_nodes(T, c):
                alim[n] = f"{C.SIGLA_REDE}-{i + 1:02d}"
    # Nós do tronco (entre a SE e as cabeças) herdam o alimentador do filho mais carregado
    for n in reversed(list(nx.topological_sort(T))):
        if n not in alim:
            filhos = sorted(T.successors(n), key=lambda f: -jusante[f])
            alim[n] = alim[filhos[0]] if filhos else f"{C.SIGLA_REDE}-01"
    return alim, jusante


def _chaves(T: nx.DiGraph, raiz, jusante: dict, alim: dict) -> list:
    """Chave no início de cada ramal (logo após uma bifurcação) com carga relevante."""
    chaves = []
    for n in T.nodes:
        if n == raiz:
            continue
        pai = next(T.predecessors(n))
        bifurca = T.out_degree(pai) >= 2 or pai == raiz
        if bifurca and MIN_UC_CHAVE <= jusante[n] <= MAX_UC_CHAVE:
            chaves.append((pai, n))
    return chaves


def construir(G=None, so_rede: bool = False):
    """Rede fictícia do município configurado. G: grafo viário pronto (fontes/osm_regiao.py); sem ele,
    o do Overpass (fontes/osm.py). so_rede: grava só subestação, média tensão, chaves e trafos (sem a
    baixa tensão nem a base de UCs, que só servem aos clientes fictícios)."""
    rng = np.random.default_rng(C.SEMENTE)
    end = gpd.read_file(C.INTERIM / "enderecos_gabarito.gpkg")
    end = end[end["COD_ESPECIE"] != "7"].reset_index(drop=True)  # obras não são clientes
    uc = end.to_crs(C.CRS_METRICO)

    uc["TRAFO_IDX"] = transformadores(uc)
    tr = uc.dissolve(by="TRAFO_IDX", aggfunc={"ZONA": "first", "COD_UNICO_ENDERECO": "count"})
    tr = tr.rename(columns={"COD_UNICO_ENDERECO": "N_UC"})
    tr["geometry"] = tr.geometry.centroid
    tr = tr.reset_index()
    tr["COD_TRAFO"] = [f"TR-{i:05d}" for i in rng.permutation(len(tr)) + 10000]

    # Grafo viário não-direcionado, em metros, só o maior componente
    G = ox.project_graph(osm.carregar() if G is None else G, to_crs=C.CRS_METRICO)
    G = ox.convert.to_undirected(G)
    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    Gs = nx.Graph()
    for u, v, d in G.edges(data=True):
        if not Gs.has_edge(u, v) or d["length"] < Gs[u][v]["length"]:
            Gs.add_edge(u, v, length=d["length"], geometry=d.get("geometry"))
    nos = ox.graph_to_gdfs(G, edges=False)

    tr["NO_VIA"] = ox.distance.nearest_nodes(G, tr.geometry.x, tr.geometry.y)

    # Subestação fictícia: no entroncamento viário mais próximo da sede
    sede = gpd.read_file(C.INTERIM / "localidades_oficiais.gpkg").to_crs(C.CRS_METRICO)
    p = sede[sede["CT_LOCALIDADE"] == "Cidade"].geometry.iloc[0]
    raiz = ox.distance.nearest_nodes(G, p.x + 1200, p.y - 600)

    carga = tr.groupby("NO_VIA")["N_UC"].sum().to_dict()
    T = _arvore_mt(Gs, raiz, set(carga))
    xy_no = {n: (G.nodes[n]["x"], G.nodes[n]["y"]) for n in T.nodes}
    alim, jusante = _alimentadores(T, raiz, carga, xy_no)
    chaves = _chaves(T, raiz, jusante, alim)

    # --- Camadas geográficas ---
    def geom_trecho(u, v):
        g = Gs[u][v].get("geometry")
        if g is None:
            return LineString([(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])])
        return g

    rede_mt = gpd.GeoDataFrame(
        {"ALIMENTADOR": [alim[v] for _, v in T.edges], "UC_JUSANTE": [jusante[v] for _, v in T.edges],
         "NO_DE": [u for u, _ in T.edges], "NO_PARA": [v for _, v in T.edges]},
        geometry=[geom_trecho(u, v) for u, v in T.edges], crs=C.CRS_METRICO,
    )

    se = gpd.GeoDataFrame({"COD_SE": [f"SE-{C.SIGLA_REDE}"], "NOME": [f"Subestação {C.NOME_MUNICIPIO} (fictícia)"]},
                          geometry=[Point(G.nodes[raiz]["x"], G.nodes[raiz]["y"])], crs=C.CRS_METRICO)

    # Chave posicionada a ~30 m do início do ramal
    reg_ch = []
    for i, (u, v) in enumerate(sorted(chaves, key=lambda e: -jusante[e[1]])):
        linha = geom_trecho(u, v)
        a = Point(G.nodes[u]["x"], G.nodes[u]["y"])
        if Point(linha.coords[0]).distance(a) > Point(linha.coords[-1]).distance(a):
            linha = LineString(linha.coords[::-1])
        reg_ch.append({"COD_CHAVE": f"CF-{i + 1:04d}", "ALIMENTADOR": alim[v], "NO_PARA": v,
                       "UC_JUSANTE": jusante[v], "geometry": linha.interpolate(min(30, linha.length / 2))})
    ch = gpd.GeoDataFrame(reg_ch, crs=C.CRS_METRICO)

    # Chave(s) a montante de cada nó: abrir qualquer uma delas desliga o nó
    no_chave = dict(zip(ch["NO_PARA"], ch["COD_CHAVE"]))
    a_jusante = {}
    for _, row in ch.iterrows():
        for n in nx.dfs_preorder_nodes(T, row["NO_PARA"]):
            a_jusante.setdefault(n, []).append(row["COD_CHAVE"])

    tr["ALIMENTADOR"] = tr["NO_VIA"].map(alim)
    tr["CHAVES_MONTANTE"] = tr["NO_VIA"].map(lambda n: ";".join(a_jusante.get(n, [])))
    uc = uc.merge(tr[["TRAFO_IDX", "COD_TRAFO", "ALIMENTADOR", "CHAVES_MONTANTE"]], on="TRAFO_IDX")

    if so_rede:
        for nome, gdf in {"subestacao": se, "rede_mt": rede_mt, "chaves": ch,
                          "transformadores": tr.drop(columns=["TRAFO_IDX"])}.items():
            gdf.to_crs(C.CRS_GEO).to_file(C.SINTETICO / f"{nome}.gpkg")
        return se, rede_mt, ch, tr, uc

    # Ramal de baixa tensão: trafo -> UC (linha reta)
    pos_tr = tr.set_index("TRAFO_IDX").geometry
    rede_bt = gpd.GeoDataFrame(
        {"COD_TRAFO": uc["COD_TRAFO"], "ZONA": uc["ZONA"]},
        geometry=[LineString([pos_tr[t], p]) for t, p in zip(uc["TRAFO_IDX"], uc.geometry)],
        crs=C.CRS_METRICO,
    )

    for nome, gdf in {"subestacao": se, "rede_mt": rede_mt, "chaves": ch,
                      "transformadores": tr.drop(columns=["TRAFO_IDX"]), "rede_bt": rede_bt}.items():
        gdf.to_crs(C.CRS_GEO).to_file(C.SINTETICO / f"{nome}.gpkg")
    uc.drop(columns=["TRAFO_IDX"]).to_crs(C.CRS_GEO).to_file(C.SINTETICO / "uc_base.gpkg")
    return se, rede_mt, ch, tr, uc


if __name__ == "__main__":
    se, rede_mt, ch, tr, uc = construir()
    print(f"UCs: {len(uc)} | trafos: {len(tr)} (rurais {(tr.ZONA == 'Rural').sum()}) | chaves: {len(ch)}")
    print(f"Rede MT: {rede_mt.length.sum() / 1000:.0f} km")
    print(tr.groupby("ALIMENTADOR")["N_UC"].agg(["count", "sum"]))
    print(tr[tr.ZONA == "Rural"]["N_UC"].describe())
    print(ch["UC_JUSANTE"].describe())
