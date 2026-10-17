"""Base territorial do município para localizar as UCs da planilha (dados reais e públicos).

Endereços do CNEFE com a comunidade já limpa (fontes/ibge.py: rótulos genéricos, nomes de
propriedade e grupos pequenos reatribuídos aos vizinhos) e o contorno do município. O mesmo nome
em distritos diferentes vira comunidades distintas ("Vista Alegre (Piacatuba)"); o aviso tira o
sufixo na hora de falar, como faz com os homônimos do algoritmo.

A validação nunca usa os mesmos endereços que montaram a base (ver validacao/planilha.py).
"""

import geopandas as gpd
import numpy as np

from .. import config as C
from ..nucleo.afetados import BaseMunicipio
from ..nucleo.nomes import exibir
from . import grafia

CRS_BASE = "EPSG:5880"   # Brasil Policônico (SIRGAS 2000), em metros: a mesma projeção para todos os municípios


def enderecos() -> gpd.GeoDataFrame:
    """Endereços do município em CRS_BASE: COMUNIDADE (com acentos e distrito nos homônimos), NM_DIST, ZONA, REATRIBUIDO."""
    g = gpd.read_file(C.INTERIM / "enderecos_gabarito.gpkg",
                      columns=["NM_DIST", "ZONA", "COMUNIDADE", "REATRIBUIDO"]).to_crs(CRS_BASE)
    acentos = grafia.carregar()
    g["COMUNIDADE"] = g["COMUNIDADE"].map(lambda n: exibir(n, acentos))
    distritos = g.groupby("COMUNIDADE")["NM_DIST"].nunique()
    homonimo = g["COMUNIDADE"].map(distritos) > 1
    g.loc[homonimo, "COMUNIDADE"] = g.loc[homonimo, "COMUNIDADE"] + " (" + g.loc[homonimo, "NM_DIST"] + ")"
    return g


def contorno():
    return gpd.read_file(C.INTERIM / "municipio.gpkg").to_crs(CRS_BASE).union_all()


def base(e: gpd.GeoDataFrame | None = None, usar: np.ndarray | None = None, limite=None) -> BaseMunicipio:
    """Base do município configurado. usar: máscara dos endereços que entram (padrão: todos);
    limite: o contorno já lido (para não reler a cada base montada na validação)."""
    e = enderecos() if e is None else e
    if usar is not None:
        e = e[usar]
    return BaseMunicipio(codigo=C.COD_MUNICIPIO, nome=C.NOME_MUNICIPIO, uf=C.UF,
                         contorno=contorno() if limite is None else limite,
                         xy=np.c_[e.geometry.x, e.geometry.y], comunidade=e["COMUNIDADE"].to_numpy(dtype=object),
                         distrito=e["NM_DIST"].to_numpy(dtype=object))
