"""Ponto da obra: trecho de média tensão mais próximo e chave de menor abrangência.

Puro: recebe os trechos (listas de [lon, lat], os mesmos desenhados no mapa), os fatores
de conversão graus -> metros e, para cada chave, os trechos que ela desliga e as contagens.
Só soma, multiplicação, divisão e raiz: o navegador repete o mesmo cálculo e chega aos
mesmos números, sem diferença de arredondamento.
"""

import math

# Pontos colados na divisa contam como dentro: o contorno do mapa é simplificado (20 m)
MARGEM_DIVISA_M = 50.0


def fatores_metros(lat_ref: float) -> tuple[float, float]:
    """(kx, ky): metros por grau de longitude e de latitude perto de lat_ref.
    Aproximação plana; dentro de um município o erro é bem menor que 1%."""
    ky = 111_320.0
    return ky * math.cos(math.radians(lat_ref)), ky


def _dist_segmento(lat: float, lon: float, p1, p2, kx: float, ky: float) -> float:
    """Distância em metros do ponto ao segmento p1-p2 ([lon, lat])."""
    ax, ay = (p1[0] - lon) * kx, (p1[1] - lat) * ky
    bx, by = (p2[0] - lon) * kx, (p2[1] - lat) * ky
    dx, dy = bx - ax, by - ay
    comp = dx * dx + dy * dy
    t = 0.0 if comp == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / comp))
    px, py = ax + t * dx, ay + t * dy
    return math.sqrt(px * px + py * py)


def trecho_mais_proximo(lat: float, lon: float, trechos: list, kx: float, ky: float) -> tuple[int, float]:
    """Índice do trecho mais próximo do ponto e a distância em metros (empate: o de menor índice)."""
    melhor, dmin = -1, math.inf
    for i, coords in enumerate(trechos):
        for p1, p2 in zip(coords, coords[1:]):
            d = _dist_segmento(lat, lon, p1, p2, kx, ky)
            if d < dmin:
                melhor, dmin = i, d
    return melhor, dmin


def _no_anel(lat: float, lon: float, anel: list) -> bool:
    dentro = False
    for (xi, yi), (xj, yj) in zip(anel, [anel[-1]] + anel[:-1]):
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
    return dentro


def dentro_da_area(lat: float, lon: float, poligonos: list, kx: float, ky: float,
                   margem_m: float = MARGEM_DIVISA_M) -> bool:
    """Ponto dentro do contorno (lista de polígonos, cada um uma lista de anéis [lon, lat]; o primeiro é
    o externo) ou a até margem_m da borda."""
    for aneis in poligonos:
        if _no_anel(lat, lon, aneis[0]) and not any(_no_anel(lat, lon, b) for b in aneis[1:]):
            return True
    return any(_dist_segmento(lat, lon, p1, p2, kx, ky) <= margem_m
               for aneis in poligonos for anel in aneis for p1, p2 in zip(anel, anel[1:]))


def poligonos_de_geojson(geometrias: list) -> list:
    """Geometrias GeoJSON (Polygon/MultiPolygon) -> lista de polígonos (listas de anéis)."""
    out = []
    for g in geometrias:
        out += [g["coordinates"]] if g["type"] == "Polygon" else list(g["coordinates"]) if g["type"] == "MultiPolygon" else []
    return out


def chaves_que_desligam(trecho: int, cenarios: dict) -> list[dict]:
    """Chaves a montante do trecho (as que o desligam), da que deixa menos clientes sem luz para a
    que deixa mais. cenarios: {cod: {"mt": [trechos], "n": clientes, "n_cit": comunidades no aviso}}."""
    lista = [{"chave": cod, "clientes": c["n"], "comunidades": c["n_cit"]}
             for cod, c in cenarios.items() if trecho in c["mt"]]
    return sorted(lista, key=lambda x: (x["clientes"], x["comunidades"], x["chave"]))


def analisar(lat: float, lon: float, trechos: list, kx: float, ky: float, raio_m: float, cenarios: dict,
             area: list | None = None) -> dict:
    """'fora' (fora da área carregada, com margem), 'longe' (sem rede a menos de raio_m),
    'tronco' (nenhuma chave de ramal isola o trecho) ou 'ok'. area: polígonos do município."""
    if area is not None and not dentro_da_area(lat, lon, area, kx, ky):
        return {"situacao": "fora", "trecho": -1, "distancia_m": None, "chaves": []}
    trecho, dist = trecho_mais_proximo(lat, lon, trechos, kx, ky)
    if trecho < 0 or dist > raio_m:
        return {"situacao": "longe", "trecho": trecho, "distancia_m": dist, "chaves": []}
    chaves = chaves_que_desligam(trecho, cenarios)
    return {"situacao": "ok" if chaves else "tronco", "trecho": trecho, "distancia_m": dist, "chaves": chaves}
