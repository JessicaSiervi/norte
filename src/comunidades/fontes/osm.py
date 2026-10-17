"""Malha viária REAL do OpenStreetMap do município (base para traçar a rede elétrica fictícia)."""

import geopandas as gpd
import networkx as nx
import osmnx as ox

from .. import config as C

# Inclui estradas de terra (track) e acessos (service): na zona rural é por elas que a rede passa
FILTRO_VIAS = (
    '["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential|'
    'living_street|service|track|road|motorway_link|trunk_link|primary_link|'
    'secondary_link|tertiary_link"]'
)
ARQ_GRAFO = C.INTERIM / "vias.graphml"
ARQ_VIAS = C.INTERIM / "vias.gpkg"


def baixar() -> nx.MultiDiGraph:
    mun = gpd.read_file(C.INTERIM / "municipio.gpkg").to_crs(C.CRS_METRICO)
    area = mun.buffer(1000).to_crs(C.CRS_WEB).iloc[0]
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(C.RAW / "osm_cache")
    G = ox.graph_from_polygon(area, custom_filter=FILTRO_VIAS, simplify=True, retain_all=False)
    ox.save_graphml(G, ARQ_GRAFO)
    ruas = ox.graph_to_gdfs(G, nodes=False)
    ruas[["highway", "name", "length", "geometry"]].assign(
        highway=lambda d: d.highway.astype(str), name=lambda d: d.name.astype(str)
    ).to_file(ARQ_VIAS)
    return G


def carregar() -> nx.MultiDiGraph:
    if ARQ_GRAFO.exists() and ARQ_VIAS.exists():
        return ox.load_graphml(ARQ_GRAFO)
    return baixar()


if __name__ == "__main__":
    G = baixar()
    ruas = gpd.read_file(ARQ_VIAS)
    print(f"Nós: {G.number_of_nodes()} | trechos: {G.number_of_edges()} | km: {ruas['length'].sum() / 1000:.0f}")
    print(ruas["highway"].value_counts().head(12))
