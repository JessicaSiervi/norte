"""Desligamento por área: 200 áreas sorteadas e o resultado esperado, para o teste JS × Python.

As áreas são polígonos que aproximam círculos (centro numa UC sorteada ou em qualquer ponto do
município, meio a meio; raio de 150 m a 3 km; de 8 a 48 vértices), com semente fixa. A cada 20,
uma vem em dois polígonos (MultiPolygon) e outra com um buraco no meio. Mais dois casos fixos: uma área fora do município e uma que
engloba o município inteiro.

O esperado é calculado pelas regras de sempre (desligamento.resumir, o aviso nos 3 idiomas, a
janela e o tamanho do aviso de hoje, contado no texto montado), sobre as UCs que nucleo/area.py põe dentro da área. As coordenadas das UCs e o contorno
do município são lidos do próprio mapa gerado, para os dois lados usarem exatamente os mesmos números.

Uso: py -m uv run python -m comunidades.validacao.area (gera o mapa antes)
"""

import json
import math
import random
import re

from .. import config as C
from .. import distribuidora as dist_
from ..apresentacao.mapa import ARQ_SAIDA
from ..nucleo import area as A
from ..nucleo.abrangencia import poligonos_de_geojson
from ..nucleo.desligamento import aviso_novo, codigos_locais, resumir
from . import referencias as R
from .avaliacao import avaliar

N_AREAS = 200
RAIO_M = (150.0, 3000.0)
VERTICES = (8, 48)
ARQUIVO = R.PASTA / "areas.json"


def dados_do_mapa() -> dict:
    html = ARQ_SAIDA.read_text(encoding="utf-8")
    return json.loads(re.search(r"const D = (\{.*?\});\n", html, flags=re.S).group(1))


def _circulo(lon: float, lat: float, raio_m: float, n: int, kx: float, ky: float, sentido: int = 1) -> list:
    anel = [[lon + raio_m * math.cos(sentido * 2 * math.pi * k / n) / kx,
             lat + raio_m * math.sin(sentido * 2 * math.pi * k / n) / ky] for k in range(n)]
    return anel + [anel[0]]


def sortear_areas(municipio: list, kx: float, ky: float, lats: list, lons: list, semente: int = C.SEMENTE) -> list[dict]:
    rnd = random.Random(semente)
    x0, y0, x1, y1 = A.caixa(municipio)

    def centro():
        # metade sobre uma UC sorteada (onde há clientes), metade em qualquer ponto do município
        if rnd.random() < 0.5:
            i = rnd.randrange(len(lats))
            return lons[i], lats[i]
        while True:
            lon, lat = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
            if any(A.no_poligono(lat, lon, m) for m in municipio):
                return lon, lat

    areas = []
    for i in range(N_AREAS):
        lon, lat = centro()
        raio = math.exp(rnd.uniform(math.log(RAIO_M[0]), math.log(RAIO_M[1])))
        n = rnd.randint(*VERTICES)
        polis = [[_circulo(lon, lat, raio, n, kx, ky)]]
        tipo = "circulo"
        if i % 20 == 7:  # dois círculos: MultiPolygon
            lon2, lat2 = centro()
            polis.append([_circulo(lon2, lat2, raio, n, kx, ky)])
            tipo = "dois_poligonos"
        elif i % 20 == 13:  # com buraco no meio (anel interno no sentido contrário)
            polis[0].append(_circulo(lon, lat, raio * 0.4, n, kx, ky, -1))
            tipo = "com_buraco"
        areas.append({"id": f"A{i + 1:03d}", "tipo": tipo, "poligonos": A.arredondar(polis)})
    # casos fixos: fora do município (20 km a leste da caixa) e engloba o município inteiro
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    areas.append({"id": "FORA", "tipo": "fora", "poligonos": A.arredondar([[_circulo(x1 + 20_000 / kx, cy, 2000, 24, kx, ky)]])})
    raio_total = math.hypot((x1 - x0) * kx, (y1 - y0) * ky)
    areas.append({"id": "MUNICIPIO", "tipo": "municipio_inteiro", "poligonos": A.arredondar([[_circulo(cx, cy, raio_total, 64, kx, ky)]])})
    return areas


def _esperado(area: dict, df, lats: list, lons: list, municipio: list, kx: float, ky: float, dist, locais) -> dict:
    r = A.analisar(lats, lons, area["poligonos"], municipio, kx, ky)
    out = {"situacao": r["situacao"], "ucs": r["ucs"], "resumo": A.resumo_da_area(area["poligonos"])}
    if r["situacao"] != "ok":
        return out
    sub = df.iloc[r["ucs"]]
    res = resumir(sub, df, dist.regras)
    out["com"] = [[c.COMUNIDADE_PREVISTA, int(c.UC_AFETADAS), int(c.UC_TOTAL), bool(c.PARCIAL), bool(c.FRAGMENTO), c.DISTRITO]
                  for c in res.itertuples()]
    out["aviso"] = aviso_novo(res, "12/11", "8h às 14h", dist.regras)
    out["avisos_idiomas"] = R.avisos_idiomas_de(area["id"], res, dist)
    cont = R.contagem_atividades(sub, list(dist.perfis))
    out["ativ"] = [cont[a] for a in dist.perfis]
    out["janelas"] = R.janelas_de(area["id"], cont, dist.perfis, dist.expediente)
    out["alimentadores"] = sorted(sub["ALIMENTADOR"].unique())
    codigos, palavras = locais
    out["hoje"] = R.tamanho_hoje_de(area["id"], sub, [codigos[i] for i in r["ucs"]], palavras, dist.regras)
    return out


def gerar(dist=None) -> dict:
    dist = dist or dist_.carregar()
    df, _, _, _ = avaliar(dist)
    D = dados_do_mapa()
    if len(D["ucs"]) != len(df):
        raise SystemExit("O mapa não corresponde ao cadastro atual: gere o mapa de novo (--so-algoritmo).")
    municipio = poligonos_de_geojson([f["geometry"] for f in D["camadas"]["municipio"]["features"]])
    kx, ky = D["rede"]["kx"], D["rede"]["ky"]
    lats, lons = [u[0] for u in D["ucs"]], [u[1] for u in D["ucs"]]
    areas = sortear_areas(municipio, kx, ky, lats, lons)
    locais = codigos_locais(df)
    for a in areas:
        a["esperado"] = _esperado(a, df, lats, lons, municipio, kx, ky, dist, locais)
    return {"municipio": dist.municipio, "semente": C.SEMENTE, "areas": areas}


if __name__ == "__main__":
    r = gerar()
    situacoes = {}
    for a in r["areas"]:
        situacoes[a["esperado"]["situacao"]] = situacoes.get(a["esperado"]["situacao"], 0) + 1
    ok = [a["esperado"] for a in r["areas"] if a["esperado"]["situacao"] == "ok"]
    print(f"{len(r['areas'])} áreas ({N_AREAS} sorteadas + 2 fixas) em {r['municipio']}: {situacoes}")
    if ok:
        n = sorted(len(e["ucs"]) for e in ok)
        print(f"Clientes por área com clientes: mínimo {n[0]}, mediana {n[len(n) // 2]}, máximo {n[-1]}")
    print(f"Gravado: {R.gravar(R.PASTA, ARQUIVO.name, r)}")
