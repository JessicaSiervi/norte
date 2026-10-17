"""Ponto da obra: 200 pontos sorteados e o resultado esperado, para o teste JS × Python.

Metade dos pontos cai perto da rede (um vértice sorteado da média tensão, deslocado até 400 m),
a outra metade em qualquer ponto da caixa do município (alguns ficam fora dele ou longe da rede).
Semente fixa. O esperado vem de nucleo/abrangencia.analisar, com os trechos, as chaves e o
contorno do município lidos do próprio mapa gerado (os mesmos números que o navegador usa).

Uso: py -m uv run python -m comunidades.validacao.obra (gera o mapa antes)
"""

import math
import random

from .. import config as C
from .. import distribuidora as dist_
from ..nucleo import abrangencia as AB
from . import referencias as R
from .area import dados_do_mapa

N_PONTOS = 200
DESLOCAMENTO_M = 400.0
ARQUIVO = R.PASTA / "obra.json"


def cenarios_do_mapa(D: dict) -> dict:
    """{cod: {mt, n, n_cit}}: o que chaves_que_desligam precisa (n_cit = comunidades citadas pelo nome)."""
    return {cod: {"mt": c["mt"], "n": c["n"], "n_cit": sum(not x[5] for x in c["com"])} for cod, c in D["cenarios"].items()}


def sortear_pontos(trechos: list, municipio: list, kx: float, ky: float, semente: int = C.SEMENTE) -> list:
    rnd = random.Random(semente + 13)
    xs = [x for p in municipio for x, _ in p[0]]
    ys = [y for p in municipio for _, y in p[0]]
    pontos = []
    for i in range(N_PONTOS):
        if i % 2 == 0:  # perto da rede
            lon, lat = rnd.choice(rnd.choice(trechos))
            ang, d = rnd.uniform(0, 2 * math.pi), rnd.uniform(0, DESLOCAMENTO_M)
            lon, lat = lon + d * math.cos(ang) / kx, lat + d * math.sin(ang) / ky
        else:  # qualquer ponto da caixa do município
            lon, lat = rnd.uniform(min(xs), max(xs)), rnd.uniform(min(ys), max(ys))
        pontos.append([round(lat, 6), round(lon, 6)])  # como o navegador marca o ponto (6 casas)
    return pontos


def gerar(dist=None) -> dict:
    dist = dist or dist_.carregar()
    D = dados_do_mapa()
    trechos = [f["geometry"]["coordinates"] for f in D["camadas"]["mt"]["features"]]
    municipio = AB.poligonos_de_geojson([f["geometry"] for f in D["camadas"]["municipio"]["features"]])
    kx, ky, cen = D["rede"]["kx"], D["rede"]["ky"], cenarios_do_mapa(D)
    pontos = []
    for lat, lon in sortear_pontos(trechos, municipio, kx, ky):
        r = AB.analisar(lat, lon, trechos, kx, ky, dist.raio_rede_m, cen, municipio)
        pontos.append({"lat": lat, "lon": lon, "esperado": r})
    return {"municipio": dist.municipio, "semente": C.SEMENTE, "pontos": pontos}


if __name__ == "__main__":
    r = gerar()
    sit = {}
    for p in r["pontos"]:
        sit[p["esperado"]["situacao"]] = sit.get(p["esperado"]["situacao"], 0) + 1
    print(f"{len(r['pontos'])} pontos da obra em {r['municipio']}: {sit}")
    print(f"Gravado: {R.gravar(R.PASTA, ARQUIVO.name, r)}")
