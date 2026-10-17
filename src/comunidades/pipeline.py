"""Orquestração do pipeline: lê e grava os arquivos e chama cada camada do projeto.

fontes (dados reais) -> simulacao (rede e clientes fictícios) -> nucleo (regras do produto)
-> validacao (métricas) -> apresentacao (mapa e página de entrada).

O nucleo não lê nem grava arquivos: é aqui que os dados são carregados e os resultados salvos.
"""

import geopandas as gpd

from . import config as C
from . import distribuidora as dist_
from .apresentacao import admin, entrada, mapa
from .fontes import dados, grafia, ibge, osm
from .nucleo import algoritmo
from .simulacao import clientes, rede
from .validacao import avaliacao


def rodar_algoritmo():
    """Identifica as comunidades a partir do cadastro e grava ucs_comunidade.gpkg e comunidades.gpkg."""
    ucs = gpd.read_file(C.SINTETICO / "ucs.gpkg")
    trafos = gpd.read_file(C.SINTETICO / "transformadores.gpkg")
    municipio = gpd.read_file(C.INTERIM / "municipio.gpkg").to_crs(C.CRS_METRICO).union_all()
    g = algoritmo.identificar(ucs, trafos, grafia.carregar())
    g.to_crs(C.CRS_GEO).to_file(C.SAIDA / "ucs_comunidade.gpkg")
    t = algoritmo.territorios(g, municipio)
    t.to_crs(C.CRS_GEO).to_file(C.SAIDA / "comunidades.gpkg")
    return g, t


ETAPAS = [
    ("Dados do IBGE (download na primeira vez)", dados.garantir),
    ("IBGE: camadas reais e gabarito", ibge.construir),
    ("OSM: malha viária", osm.carregar),
    ("Grafia dos nomes (IBGE e OSM)", grafia.construir),
    ("Rede elétrica fictícia", rede.construir),
    ("Cadastro fictício de UCs", clientes.construir),
    ("Algoritmo de comunidades", rodar_algoritmo),
    ("Mapa interativo (inclui avaliação)", "mapa"),
    ("Área administrativa (protótipo)", admin.construir),
    ("Página de entrada (escolha da área)", entrada.construir),
]
SO_ALGORITMO = {"Algoritmo de comunidades", "Mapa interativo (inclui avaliação)", "Área administrativa (protótipo)",
                "Página de entrada (escolha da área)"}


def executar(argv: list[str]) -> None:
    """Executa o pipeline completo: dados reais -> rede fictícia -> algoritmo -> avaliação -> mapa.
    Com --so-algoritmo, reaproveita os dados e o cadastro já gerados.
    Com --distribuidora arquivo.toml, usa outra configuração (padrão: distribuidoras/demo-leopoldina.toml)."""
    pular_dados = "--so-algoritmo" in argv
    arquivo = argv[argv.index("--distribuidora") + 1] if "--distribuidora" in argv else None
    dist = dist_.carregar(arquivo)
    if arquivo:
        print(f"Distribuidora: {dist.arquivo}", flush=True)
    for nome, f in ETAPAS:
        if pular_dados and nome not in SO_ALGORITMO:
            continue
        print(f"> {nome}...", flush=True)
        mapa.construir(dist) if f == "mapa" else f()

    _, por_uc, _, cen = avaliacao.avaliar(dist)
    print("\nAcerto por UC (cadastro digitado x algoritmo):")
    print(por_uc.to_string())
    print(f"\nCenários: {len(cen)} | cobertura média {cen.COBERTURA.mean():.1%} | "
          f"precisão média {cen.PRECISAO.mean():.1%} | aviso {cen.SEG_ANTES.mean():.0f}s -> {cen.SEG_DEPOIS.mean():.0f}s")
    print(f"\nMapa: {mapa.ARQ_SAIDA}")
    print(f"Entrada: {entrada.ARQ_ENTRADA}")
    print(f"Área administrativa (protótipo): {admin.ARQ_ADMIN}")


if __name__ == "__main__":
    # Só o algoritmo, com o resumo que antes era impresso por `python -m comunidades.algoritmo`
    g, t = rodar_algoritmo()
    print(f"Comunidades identificadas: {len(t)}")
    print(g["ORIGEM_COORD"].value_counts())
    print(t.sort_values("N_UC", ascending=False).drop(columns="geometry").to_string())
