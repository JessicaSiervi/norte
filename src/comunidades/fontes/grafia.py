"""Grafia acentuada dos nomes, a partir das fontes REAIS do município.

Junta as palavras dos nomes que já vêm com acento nas vias do OpenStreetMap e nas
localidades e distritos do IBGE. Para cada palavra sem acento ("CEMITERIO"), fica a forma
acentuada mais frequente ("Cemitério"), desde que as formas acentuadas apareçam pelo menos
tantas vezes quanto a forma sem acento. Grava interim/grafia.json; o núcleo recebe o
dicionário pronto (nucleo/nomes.py usa o dicionário manual só como reserva).
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict

import geopandas as gpd

from .. import config as C

ARQ = "grafia.json"


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _textos() -> list[str]:
    # sem as vias do OSM (base territorial da concessão, que não precisa delas), só o IBGE
    vias = C.INTERIM / "vias.gpkg"
    textos = list(gpd.read_file(vias)["name"].dropna().astype(str)) if vias.exists() else []
    textos += list(gpd.read_file(C.INTERIM / "localidades_oficiais.gpkg")["NM_LOCALIDADE"].astype(str))
    textos += list(gpd.read_file(C.INTERIM / "distritos.gpkg")["NM_DIST"].astype(str))
    return [t for t in textos if t and t != "nan"]


def montar(textos: list[str]) -> dict:
    """{"CEMITERIO": "Cemitério", ...}: só palavras em que a forma acentuada é a mais comum."""
    formas = defaultdict(Counter)
    for t in textos:
        for w in re.findall(r"[^\W\d_]+", t):
            formas[_sem_acento(w).upper()][w[:1].upper() + w[1:].lower()] += 1
    grafia = {}
    for chave, c in sorted(formas.items()):
        acentuadas = Counter({f: n for f, n in c.items() if _sem_acento(f) != f})
        sem = sum(n for f, n in c.items() if _sem_acento(f) == f)
        if acentuadas and sum(acentuadas.values()) >= sem:
            grafia[chave] = acentuadas.most_common(1)[0][0]
    return grafia


def construir() -> dict:
    grafia = montar(_textos())
    (C.INTERIM / ARQ).write_text(json.dumps(grafia, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    return grafia


def carregar() -> dict:
    """O dicionário gravado; se ainda não existir (dados de antes desta etapa), monta agora."""
    arq = C.INTERIM / ARQ
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else construir()


if __name__ == "__main__":
    g = construir()
    print(f"{len(g)} palavras com grafia acentuada: {C.INTERIM / ARQ}")
