"""Rede elétrica FICTÍCIA no banco (só para demonstração no mapa): subestação, média tensão, chaves e trafos.

Nada de cliente entra aqui: a rede é traçada pelas vias reais do OSM até grupos de endereços do CNEFE
(simulacao/rede.py), e cada elemento guarda só o código, o alimentador e a contagem a jusante.
Geometrias em SIRGAS 2000 (EPSG:4674). Apagar o município (base_concessao --refazer) apaga a rede dele.

Tabelas: rede_subestacao, rede_trecho (média tensão), rede_chave e rede_trafo.
"""

import functools

import geopandas as gpd
import shapely

from .base_territorial import SRID, _colecao
from .conexao import conectar

ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS rede_subestacao (
    codigo_ibge  text PRIMARY KEY REFERENCES municipio ON DELETE CASCADE,
    codigo       text NOT NULL,
    nome         text NOT NULL,
    ponto        geometry(Point, {SRID}) NOT NULL
);
CREATE TABLE IF NOT EXISTS rede_trecho (
    codigo_ibge  text NOT NULL REFERENCES municipio ON DELETE CASCADE,
    alimentador  text NOT NULL,
    uc_jusante   integer NOT NULL,
    linha        geometry(LineString, {SRID}) NOT NULL
);
CREATE TABLE IF NOT EXISTS rede_chave (
    codigo_ibge  text NOT NULL REFERENCES municipio ON DELETE CASCADE,
    codigo       text NOT NULL,
    alimentador  text NOT NULL,
    uc_jusante   integer NOT NULL,
    ponto        geometry(Point, {SRID}) NOT NULL,
    PRIMARY KEY (codigo_ibge, codigo)
);
CREATE TABLE IF NOT EXISTS rede_trafo (
    codigo_ibge  text NOT NULL REFERENCES municipio ON DELETE CASCADE,
    codigo       text NOT NULL,
    zona         text NOT NULL,
    n_uc         integer NOT NULL,
    ponto        geometry(Point, {SRID}) NOT NULL
);
CREATE INDEX IF NOT EXISTS rede_trecho_municipio ON rede_trecho (codigo_ibge);
CREATE INDEX IF NOT EXISTS rede_trafo_municipio ON rede_trafo (codigo_ibge);
"""
SIMPLIFICAR_REDE = 0.00003   # graus (~3 m): traçado da média tensão no mapa
CASAS = 5                    # casas decimais dos pontos no mapa (cerca de 1 m)


def criar_esquema() -> None:
    with conectar() as c:
        c.execute(ESQUEMA)


def _wkb(g) -> bytes:
    return shapely.to_wkb(g)


def gravar(codigo: str, se: gpd.GeoDataFrame, rede_mt: gpd.GeoDataFrame, chaves: gpd.GeoDataFrame,
           trafos: gpd.GeoDataFrame) -> None:
    """Substitui a rede do município (numa transação só). Camadas como as de simulacao/rede.py, em EPSG:4674."""
    with conectar() as c, c.cursor() as cur:
        for t in ("rede_subestacao", "rede_trecho", "rede_chave", "rede_trafo"):
            cur.execute(f"DELETE FROM {t} WHERE codigo_ibge = %s", (codigo,))
        s = se.iloc[0]
        cur.execute("INSERT INTO rede_subestacao VALUES (%s, %s, %s, ST_GeomFromWKB(%s, %s))",
                    (codigo, s["COD_SE"], s["NOME"], _wkb(s.geometry), SRID))
        cur.executemany("INSERT INTO rede_trecho VALUES (%s, %s, %s, ST_GeomFromWKB(%s, %s))",
                        [(codigo, r.ALIMENTADOR, int(r.UC_JUSANTE), _wkb(r.geometry), SRID) for r in rede_mt.itertuples()])
        cur.executemany("INSERT INTO rede_chave VALUES (%s, %s, %s, %s, ST_GeomFromWKB(%s, %s))",
                        [(codigo, r.COD_CHAVE, r.ALIMENTADOR, int(r.UC_JUSANTE), _wkb(r.geometry), SRID) for r in chaves.itertuples()])
        cur.executemany("INSERT INTO rede_trafo VALUES (%s, %s, %s, %s, ST_GeomFromWKB(%s, %s))",
                        [(codigo, r.COD_TRAFO, r.ZONA, int(r.N_UC), _wkb(r.geometry), SRID) for r in trafos.itertuples()])


def municipios_com_rede() -> set[str]:
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT codigo_ibge FROM rede_subestacao")
        return {r[0] for r in cur.fetchall()}


@functools.lru_cache(maxsize=80)
def rede_mapa(codigo: str) -> dict | None:
    """Rede do município para o mapa: alimentadores (GeoJSON, um traçado por alimentador), subestação,
    chaves [lat, lon, código, alimentador, a jusante] e trafos [lat, lon]; None se não há rede."""
    with conectar() as c, c.cursor() as cur:
        cur.execute("SELECT codigo, nome, ROUND(ST_Y(ponto)::numeric, %s)::float8, ROUND(ST_X(ponto)::numeric, %s)::float8"
                    " FROM rede_subestacao WHERE codigo_ibge = %s", (CASAS, CASAS, codigo))
        se = cur.fetchone()
        if not se:
            return None
        cur.execute("SELECT alimentador, ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_LineMerge(ST_Collect(linha)), %s), %s)"
                    " FROM rede_trecho WHERE codigo_ibge = %s GROUP BY alimentador ORDER BY alimentador",
                    (SIMPLIFICAR_REDE, CASAS, codigo))
        alimentadores = _colecao(cur.fetchall(), ["alimentador"])
        cur.execute("SELECT ROUND(ST_Y(ponto)::numeric, %s)::float8, ROUND(ST_X(ponto)::numeric, %s)::float8,"
                    " codigo, alimentador, uc_jusante FROM rede_chave WHERE codigo_ibge = %s ORDER BY codigo",
                    (CASAS, CASAS, codigo))
        chaves = [list(r) for r in cur.fetchall()]
        cur.execute("SELECT ROUND(ST_Y(ponto)::numeric, %s)::float8, ROUND(ST_X(ponto)::numeric, %s)::float8"
                    " FROM rede_trafo WHERE codigo_ibge = %s", (CASAS, CASAS, codigo))
        trafos = [list(r) for r in cur.fetchall()]
    return {"ficticia": True, "subestacao": {"codigo": se[0], "nome": se[1], "ponto": [se[2], se[3]]},
            "alimentadores": alimentadores, "chaves": chaves, "trafos": trafos}
