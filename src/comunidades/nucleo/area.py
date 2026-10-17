"""Desligamento por área: quais clientes ficam dentro de um contorno desenhado ou importado.

Puro: recebe as coordenadas das UCs (as mesmas do mapa, com 5 casas), os polígonos da área e
o contorno do município, todos em [lon, lat]. A área NÃO segue a rede elétrica: é o operador
quem diz que aquele trecho fica sem luz. Daí em diante valem as regras de sempre
(desligamento.resumir, o aviso e a janela).

Só comparação, soma, multiplicação e divisão: o navegador repete o mesmo cálculo e chega
ao mesmo resultado, ponto a ponto.
"""

import hashlib

from .abrangencia import _no_anel, dentro_da_area

MAX_VERTICES = 20_000   # acima disso o navegador fica lento; o operador simplifica o contorno
CASAS = 6               # casas decimais das coordenadas da área (~10 cm)


def arredondar(poligonos: list) -> list:
    """Coordenadas com CASAS casas decimais (como o navegador guarda a área)."""
    return [[[[round(x, CASAS), round(y, CASAS)] for x, y in anel] for anel in p] for p in poligonos]


def n_vertices(poligonos: list) -> int:
    """Vértices de todos os anéis, sem contar o ponto que repete o primeiro para fechar o anel."""
    return sum(len(anel) - (len(anel) > 1 and anel[0] == anel[-1]) for p in poligonos for anel in p)


def caixa(poligonos: list) -> tuple:
    """(lon_min, lat_min, lon_max, lat_max) dos anéis externos."""
    xs = [x for p in poligonos for x, _ in p[0]]
    ys = [y for p in poligonos for _, y in p[0]]
    return min(xs), min(ys), max(xs), max(ys)


def no_poligono(lat: float, lon: float, aneis: list) -> bool:
    """Dentro do anel externo e fora dos buracos (sem margem: na área ou fora dela)."""
    return _no_anel(lat, lon, aneis[0]) and not any(_no_anel(lat, lon, b) for b in aneis[1:])


def ucs_na_area(lats: list, lons: list, poligonos: list) -> list[int]:
    """Índices das UCs dentro de algum dos polígonos (vários polígonos valem juntos)."""
    caixas = [caixa([p]) for p in poligonos]
    dentro = []
    for i, (lat, lon) in enumerate(zip(lats, lons)):
        for (x0, y0, x1, y1), p in zip(caixas, poligonos):
            if x0 <= lon <= x1 and y0 <= lat <= y1 and no_poligono(lat, lon, p):
                dentro.append(i)
                break
    return dentro


def toca_o_municipio(poligonos: list, municipio: list, kx: float, ky: float) -> bool:
    """Algum vértice da área dentro do município (com a margem da divisa) ou algum vértice
    do município dentro da área (área que engloba o município inteiro)."""
    if any(dentro_da_area(y, x, municipio, kx, ky) for p in poligonos for anel in p for x, y in anel):
        return True
    return any(no_poligono(y, x, p) for m in municipio for anel in m for x, y in anel for p in poligonos)


def analisar(lats: list, lons: list, poligonos: list, municipio: list, kx: float, ky: float) -> dict:
    """'vertices' (contorno grande demais), 'fora' (área fora do município carregado),
    'sem_clientes' (nenhuma UC dentro) ou 'ok', com os índices das UCs dentro."""
    if n_vertices(poligonos) > MAX_VERTICES:
        return {"situacao": "vertices", "ucs": []}
    if not toca_o_municipio(poligonos, municipio, kx, ky):
        return {"situacao": "fora", "ucs": []}
    ucs = ucs_na_area(lats, lons, poligonos)
    return {"situacao": "ok" if ucs else "sem_clientes", "ucs": ucs}


def forma_canonica(poligonos: list) -> str:
    """Texto que identifica a área no código de verificação: "lon,lat" com 6 casas, vértices
    separados por ";", anéis por "|" e polígonos por "/" (o anel fechado, como no GeoJSON)."""
    return "/".join("|".join(";".join(f"{x:.{CASAS}f},{y:.{CASAS}f}" for x, y in anel) for anel in p)
                    for p in poligonos)


def resumo_da_area(poligonos: list) -> dict:
    """Polígonos, vértices e o SHA-256 da forma canônica (o que entra no código de verificação)."""
    return {"poligonos": len(poligonos), "vertices": n_vertices(poligonos),
            "sha256": hashlib.sha256(forma_canonica(poligonos).encode("utf-8")).hexdigest()}
