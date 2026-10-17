"""Malha viária REAL do OpenStreetMap da área de concessão, de um arquivo regional (sem Overpass).

- Baixa uma vez o recorte do Sudeste da Geofabrik (MG e RJ; não há recorte por estado) para
  data/raw/osm/ e confere o MD5 publicado ao lado.
- Extrai, numa passada só, as vias da área de concessão (mesmo filtro de fontes/osm.py: inclui
  estradas de terra e acessos) para data/raw/osm/vias_concessao.gpkg. Depois disso, o .pbf pode
  ser apagado.
- grafo(area) monta, para um município, o grafo viário no formato do osmnx: nós nos cruzamentos e
  nas pontas, arestas com a geometria do trecho e o comprimento em metros (base da rede fictícia).

Dados © colaboradores do OpenStreetMap (ODbL): quem mostrar a rede tem de dar o crédito.
Uso: uv run python -m comunidades.fontes.osm_regiao   (baixa e extrai)
"""

import hashlib
import shutil
import urllib.request
from collections import Counter
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pyogrio
import shapely
from shapely.geometry import LineString

from .. import config as C
from . import concessao

URL = "https://download.geofabrik.de/south-america/brazil/sudeste-latest.osm.pbf"
PASTA = C.RAW / "osm"
ARQ_PBF = PASTA / "sudeste-latest.osm.pbf"
ARQ_VIAS = PASTA / "vias_concessao.gpkg"
MARGEM_GRAUS = 0.05              # ~5 km além do contorno da concessão
# os mesmos tipos de via de fontes/osm.py (FILTRO_VIAS)
TIPOS = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
         "living_street", "service", "track", "road", "motorway_link", "trunk_link", "primary_link",
         "secondary_link", "tertiary_link")


def _md5(arq: Path) -> str:
    h = hashlib.md5()
    with open(arq, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 22), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar() -> Path:
    """O .pbf do Sudeste, conferido pelo MD5 da Geofabrik (baixa só se faltar)."""
    if ARQ_PBF.exists():
        return ARQ_PBF
    PASTA.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL + ".md5", timeout=60) as r:
        esperado = r.read().decode().split()[0]
    print(f"  baixando {ARQ_PBF.name} (Geofabrik, ~820 MB)...", flush=True)
    tmp = ARQ_PBF.with_suffix(".parcial")
    with urllib.request.urlopen(URL, timeout=600) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 22)
    if _md5(tmp) != esperado:
        tmp.unlink()
        raise RuntimeError(f"{ARQ_PBF.name}: MD5 não confere com o da Geofabrik (arquivo apagado; baixe de novo)")
    tmp.replace(ARQ_PBF)
    return ARQ_PBF


def extrair() -> Path:
    """Vias da área de concessão (osm_id, highway, geometria) num GeoPackage com índice espacial."""
    if ARQ_VIAS.exists():
        return ARQ_VIAS
    pbf = baixar()
    x0, y0, x1, y1 = concessao.contorno().bounds
    tipos = ", ".join(f"'{t}'" for t in TIPOS)
    print("  extraindo as vias da área de concessão (uma passada no .pbf)...", flush=True)
    vias = pyogrio.read_dataframe(pbf, layer="lines", columns=["osm_id", "highway"],
                                  bbox=(x0 - MARGEM_GRAUS, y0 - MARGEM_GRAUS, x1 + MARGEM_GRAUS, y1 + MARGEM_GRAUS),
                                  where=f"highway IN ({tipos})")
    vias = vias[vias.geometry.geom_type == "LineString"].set_crs(C.CRS_WEB, allow_override=True).to_crs(C.CRS_GEO)
    tmp = ARQ_VIAS.with_suffix(".parcial.gpkg")
    vias.to_file(tmp, driver="GPKG")
    tmp.replace(ARQ_VIAS)
    print(f"  {len(vias)} vias -> {ARQ_VIAS}", flush=True)
    return ARQ_VIAS


def grafo(area) -> nx.MultiDiGraph:
    """Grafo viário (formato do osmnx, em EPSG:4674) das vias que tocam `area` (polígono em EPSG:4674).

    Nós: cruzamentos (vértice compartilhado por mais de uma via ou repetido na mesma) e pontas; arestas:
    o trecho entre dois nós, com a geometria e o comprimento em metros (na projeção do município)."""
    vias = gpd.read_file(extrair(), bbox=tuple(area.bounds))
    vias = vias[vias.intersects(area)]
    metrico = vias.to_crs(C.CRS_METRICO).geometry
    coords = [np.asarray(g.coords) for g in vias.geometry]
    coords_m = [np.asarray(g.coords) for g in metrico]
    uso = Counter(tuple(p) for c in coords for p in c)
    G = nx.MultiDiGraph(crs=C.CRS_GEO)
    for osmid, c, cm in zip(vias["osm_id"].astype("int64").tolist(), coords, coords_m):
        corte = [0] + [i for i in range(1, len(c) - 1) if uso[tuple(c[i])] > 1] + [len(c) - 1]
        for a, b in zip(corte[:-1], corte[1:]):
            u, v = tuple(c[a]), tuple(c[b])
            if u == v:
                continue
            for n in (u, v):
                if n not in G:
                    G.add_node(n, x=n[0], y=n[1])
            trecho = c[a:b + 1]
            comprimento = float(shapely.length(LineString(cm[a:b + 1])))
            G.add_edge(u, v, osmid=osmid, length=comprimento, geometry=LineString(trecho))
            G.add_edge(v, u, osmid=osmid, length=comprimento, geometry=LineString(trecho[::-1]))
    # nós com número inteiro, como os do osmnx (o grafo projetado e o nearest_nodes esperam isso)
    return nx.convert_node_labels_to_integers(G)


if __name__ == "__main__":
    extrair()
