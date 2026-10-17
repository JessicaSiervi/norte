"""Planilhas de UCs afetadas para teste, a partir da rede e do cadastro FICTÍCIOS.

Para uma chave da rede fictícia, as UCs a jusante viram uma planilha no modelo provisório
(uc, latitude, longitude, equipamento_vital, classe, local), com a coordenada real do endereço do
CNEFE de onde a UC fictícia saiu. local é o que o aviso de hoje cita (o imóvel, senão a rua, do
cadastro fictício; nunca o titular), para o comparativo. ruido_m imita o erro de GPS (deslocamento aleatório de até
tantos metros). equipamento_vital é sorteado (FRACAO_VITAL) só para exercitar o prazo de 5 dias
úteis: não vem de nenhum dado real. Grava em saida/planilhas_teste/ (fora do git).

Uso: uv run python -m comunidades.simulacao.planilhas_teste CF-0066 [--ruido 15]
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import config as C
from ..nucleo.desligamento import _local_bruto, ucs_afetadas

PASTA = C.SAIDA / "planilhas_teste"
FRACAO_VITAL = 0.01


def planilha(chave: str, ruido_m: float = 0.0) -> pd.DataFrame:
    ucs = gpd.read_file(C.SINTETICO / "ucs.gpkg", columns=["UC", "CLASSE", "CHAVES_MONTANTE", "NOME_IMOVEL", "LOGRADOURO"], ignore_geometry=True)
    gab = pd.read_csv(C.SINTETICO / "gabarito_uc.csv", dtype={"UC": str}, usecols=["UC", "LAT_REAL", "LON_REAL"])
    af = ucs_afetadas(ucs.merge(gab, on="UC"), chave)
    if af.empty:
        raise ValueError(f"Nenhuma UC a jusante da chave {chave}.")
    rng = np.random.default_rng(C.SEMENTE)
    lat, lon = af["LAT_REAL"].to_numpy(), af["LON_REAL"].to_numpy()
    if ruido_m:
        ang, dist = rng.uniform(0, 2 * np.pi, len(af)), ruido_m * np.sqrt(rng.uniform(0, 1, len(af)))
        lat = lat + dist * np.sin(ang) / 111_320
        lon = lon + dist * np.cos(ang) / (111_320 * np.cos(np.radians(lat)))
    return pd.DataFrame({"uc": af["UC"].to_numpy(), "latitude": lat.round(6), "longitude": lon.round(6),
                         "equipamento_vital": np.where(rng.random(len(af)) < FRACAO_VITAL, "sim", "não"),
                         "classe": af["CLASSE"].str.lower().to_numpy(), "local": _local_bruto(af).fillna("").to_numpy()})


def gravar(chave: str, ruido_m: float = 0.0) -> tuple:
    PASTA.mkdir(parents=True, exist_ok=True)
    t = planilha(chave, ruido_m)
    nome = f"planilha_{chave}" + (f"_ruido{ruido_m:g}m" if ruido_m else "")
    csv, xlsx = PASTA / f"{nome}.csv", PASTA / f"{nome}.xlsx"
    t.to_csv(csv, sep=";", decimal=",", index=False, encoding="utf-8-sig")  # como o Excel brasileiro grava
    t.to_excel(xlsx, index=False)
    return csv, xlsx, len(t)


if __name__ == "__main__":
    args = sys.argv[1:]
    ruido = float(args[args.index("--ruido") + 1]) if "--ruido" in args else 0.0
    for chave in [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--ruido")] or ["CF-0066"]:
        csv, xlsx, n = gravar(chave, ruido)
        print(f"{chave}: {n} UCs fictícias -> {csv} e {xlsx.name}")
