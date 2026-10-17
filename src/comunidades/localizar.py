"""Descobre o município de uma coordenada pela malha municipal do IBGE e escolhe a distribuidora.

A malha (API de malhas do IBGE, qualidade intermediária) e a lista de municípios (API de
localidades) são baixadas uma vez e guardadas em data/raw/malha_municipal/.
Não importa config.py: roda antes de o município ser escolhido.
"""

import gzip
import json
import re
import shutil
import tomllib
import unicodedata
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PASTA_MALHA = RAIZ / "data" / "raw" / "malha_municipal"
ARQ_MALHA = PASTA_MALHA / "BR_municipios_intermediaria.geojson"
ARQ_NOMES = PASTA_MALHA / "municipios.json"
DISTRIBUIDORAS = RAIZ / "distribuidoras"
BASE = DISTRIBUIDORAS / "demo-leopoldina.toml"   # valores usados para criar o arquivo de um município novo

URL_MALHA = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson"
             "&qualidade=intermediaria&intrarregiao=municipio")
URL_NOMES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"


class ForaDoBrasil(ValueError):
    pass


def _baixar(url: str, destino: Path):
    PASTA_MALHA.mkdir(parents=True, exist_ok=True)
    print(f"  baixando {destino.name} do IBGE (só na primeira vez)...", flush=True)
    tmp = destino.with_suffix(".parcial")
    with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    with open(tmp, "rb") as f:
        comprimido = f.read(2) == b"\x1f\x8b"  # a API do IBGE responde em gzip mesmo sem pedir
    if comprimido:
        with gzip.open(tmp, "rb") as g, open(destino, "wb") as f:
            shutil.copyfileobj(g, f, length=1 << 20)
        tmp.unlink()
    else:
        tmp.replace(destino)


def ler_coordenada(texto: str) -> tuple[float, float]:
    """'-21.13,-42.37' -> (lat, lon), com mensagem clara se estiver malformada."""
    partes = [p.strip() for p in texto.split(",")]
    try:
        lat, lon = float(partes[0]), float(partes[1])
        assert len(partes) == 2 and -90 <= lat <= 90 and -180 <= lon <= 180
    except (ValueError, IndexError, AssertionError):
        raise ValueError(f'coordenada inválida: "{texto}". Use "latitude,longitude", por exemplo "-21.13,-42.37".')
    return lat, lon


def municipio_da_coordenada(lat: float, lon: float) -> dict:
    """{'codigo', 'nome', 'uf'} do município que contém o ponto, ou ForaDoBrasil."""
    import geopandas as gpd
    from shapely.geometry import Point

    if not ARQ_MALHA.exists():
        _baixar(URL_MALHA, ARQ_MALHA)
    if not ARQ_NOMES.exists():
        _baixar(URL_NOMES, ARQ_NOMES)
    malha = gpd.read_file(ARQ_MALHA)
    achados = malha[malha.contains(Point(lon, lat))]
    if achados.empty:
        raise ForaDoBrasil(f"a coordenada ({lat}, {lon}) não cai em nenhum município brasileiro "
                           f"(malha municipal do IBGE). Confira se a ordem é latitude,longitude.")
    codigo = str(achados.iloc[0]["codarea"])
    m = next(x for x in json.loads(ARQ_NOMES.read_text(encoding="utf-8")) if str(x["id"]) == codigo)
    return {"codigo": codigo, "nome": m["nome"], "uf": m["microrregiao"]["mesorregiao"]["UF"]["sigla"]}


def _slug(nome: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", nome) if unicodedata.category(c) != "Mn")
    return "-".join(s.lower().replace("'", " ").split())


def distribuidora_do_municipio(mun: dict) -> tuple[Path, bool]:
    """Arquivo de distribuidora do município (o que já existe ou um novo). Devolve (caminho, criado)."""
    for arq in sorted(DISTRIBUIDORAS.glob("*.toml")):
        if arq.name == "MODELO.toml":
            continue
        with open(arq, "rb") as f:
            if str(tomllib.load(f).get("distribuidora", {}).get("codigo_ibge")) == mun["codigo"]:
                return arq, False
    # Novo: estrutura do MODELO com os valores do demo-leopoldina, trocando só município, UF e código
    texto = BASE.read_text(encoding="utf-8")
    trocas = {"municipio": mun["nome"], "uf": mun["uf"], "codigo_ibge": mun["codigo"]}
    for campo, valor in trocas.items():
        texto, n = re.subn(rf'^{campo} = "[^"]*"', f'{campo} = "{valor}"', texto, count=1, flags=re.M)
        assert n == 1, campo
    aviso = (f"# CRIADO AUTOMATICAMENTE a partir da coordenada, para {mun['nome']}/{mun['uf']} ({mun['codigo']}).\n"
             "# Estrutura do MODELO.toml com os valores do demo-leopoldina; só município, UF e código foram trocados.\n"
             "# REVISE os campos da distribuidora (nome, assinatura, telefone, prazos e perfis) antes de usar.\n\n")
    destino = DISTRIBUIDORAS / f"auto-{_slug(mun['nome'])}.toml"
    destino.write_text(aviso + texto, encoding="utf-8")
    return destino, True
