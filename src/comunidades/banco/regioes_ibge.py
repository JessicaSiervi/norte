"""Regiões do IBGE (só dados públicos): microrregiões e regiões geográficas imediatas, para a camada "Regiões do IBGE" do mapa.

A microrregião é a divisão de 1989, que o IBGE deixou de atualizar; a região imediata (2017) é a que a substitui. As duas
ficam aqui, com o contorno (junção dos municípios, simplificado para a tela), um ponto dentro (onde escrever o nome) e a
lista dos municípios de cada uma (para filtrar pela área de atuação da empresa). Nada de cliente. Não mudam o aviso.
Carga: uv run python -m comunidades.municipios_brasil (junto com os municípios; as malhas ficam em data/raw/malhas).

Tabela: regiao_ibge.
"""

import json

import psycopg
import shapely

from .conexao import conectar

SRID = 4674
SIMPLIFICAR = 0.002   # graus (cerca de 200 m), como os municípios do Brasil (municipios_ibge.py)
TIPOS = ("micro", "imediata")
NOME_TIPO = {"micro": "Microrregião", "imediata": "Região geográfica imediata"}

ESQUEMA = f"""
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS regiao_ibge (
    tipo        text NOT NULL CHECK (tipo IN ('micro', 'imediata')),
    codigo      text NOT NULL CHECK (codigo ~ '^[0-9]{{5,6}}$'),
    nome        text NOT NULL,
    uf          text NOT NULL CHECK (uf ~ '^[A-Z]{{2}}$'),
    municipios  text[] NOT NULL,
    contorno    geometry(MultiPolygon, {SRID}) NOT NULL,
    ponto       geometry(Point, {SRID}) NOT NULL,
    PRIMARY KEY (tipo, codigo)
);
CREATE INDEX IF NOT EXISTS regiao_ibge_uf ON regiao_ibge (uf);
CREATE INDEX IF NOT EXISTS regiao_ibge_municipios ON regiao_ibge USING gin (municipios);
"""


def criar_esquema() -> None:
    with conectar() as c:
        c.execute(ESQUEMA)


def ufs_gravadas() -> set[str]:
    with conectar() as c:
        return {r[0] for r in c.execute("SELECT DISTINCT uf FROM regiao_ibge").fetchall()}


def gravar_uf(uf: str, regioes) -> int:
    """Substitui as regiões da UF (GeoDataFrame de fontes.concessao.regioes_uf: TIPO, CODIGO, NOME, MUNICIPIOS e geometry)."""
    linhas = []
    for r in regioes.itertuples():
        g = shapely.make_valid(shapely.simplify(r.geometry, SIMPLIFICAR, preserve_topology=True))
        g = shapely.MultiPolygon([p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon"])
        linhas.append((r.TIPO, r.CODIGO, r.NOME, uf, list(r.MUNICIPIOS), shapely.to_wkb(g), shapely.to_wkb(g.point_on_surface())))
    with conectar() as c, c.cursor() as cur:
        cur.execute("DELETE FROM regiao_ibge WHERE uf = %s", (uf,))
        cur.executemany("INSERT INTO regiao_ibge (tipo, codigo, nome, uf, municipios, contorno, ponto) VALUES (%s, %s, %s, %s, %s,"
                        f" ST_SetSRID(ST_GeomFromWKB(%s), {SRID}), ST_SetSRID(ST_GeomFromWKB(%s), {SRID}))", linhas)
    return len(linhas)


def para_o_mapa(tipo: str, codigos: list[str]) -> dict:
    """As regiões do tipo que têm algum município da lista (a área da empresa): contorno, ponto (onde escrever o nome),
    quantos municípios a região tem e quantos deles estão na lista."""
    try:
        linhas = _consultar(tipo, codigos)
    except psycopg.errors.UndefinedTable:   # carga ainda não feita: a camada fica vazia, sem erro na tela
        linhas = []
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codigo": r[0], "nome": r[1], "uf": r[2], "municipios": r[3], "na_area": r[4],
                                           "ponto": [round(r[6], 5), round(r[5], 5)]},
         "geometry": json.loads(r[7])} for r in linhas]}


def _consultar(tipo: str, codigos: list[str]) -> list[tuple]:
    with conectar() as c:
        return c.execute("SELECT codigo, nome, uf, cardinality(municipios), cardinality(ARRAY(SELECT unnest(municipios)"
                         " INTERSECT SELECT unnest(%s::text[]))), ST_X(ponto), ST_Y(ponto), ST_AsGeoJSON(contorno, 4)"
                         " FROM regiao_ibge WHERE tipo = %s AND municipios && %s::text[] ORDER BY uf, nome",
                         (list(codigos), tipo, list(codigos))).fetchall()


def totais() -> dict:
    with conectar() as c:
        return {t: n for t, n in c.execute("SELECT tipo, count(*) FROM regiao_ibge GROUP BY tipo ORDER BY tipo").fetchall()}
