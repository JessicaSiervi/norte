"""Avaliação da localização pela planilha de UCs afetadas (base territorial do CNEFE).

A base e o gabarito vêm do mesmo CNEFE, então a regra é nunca validar com os endereços que
montaram a base:
1. Amostra separada: base com 80% dos endereços (sorteio fixo) e acerto nos outros 20%. Só contam
   os endereços com o rótulo original válido (REATRIBUIDO falso): os reatribuídos já foram
   deduzidos dos vizinhos na limpeza do gabarito, e acertá-los seria fácil demais.
2. Planilhas de teste: para cada chave da rede fictícia, as UCs a jusante com a coordenada real
   viram uma planilha. Cada UC é localizada com uma base sem o próprio endereço (os endereços são
   divididos em 5 partes; a UC usa a base sem a parte dela), mas com os vizinhos, como na vida
   real. As métricas são as do avaliacao.py (lidas de saida/avaliacao_cenarios.csv), lado a lado.

Uso: py -m uv run python -m comunidades.validacao.planilha
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.neighbors import KDTree

from .. import config as C
from .. import distribuidora as dist_
from ..fontes import base_territorial as BT
from ..nucleo.afetados import avisar, comunidade_de, localizar
from ..nucleo.desligamento import ucs_afetadas
from .avaliacao import _alinhar, _chave_nome

FRACAO_TESTE = 0.2
PARTES = 5                    # planilhas de teste: cada UC localizada sem a parte do próprio endereço
RAIO_MESMO_ENDERECO_M = 1.0   # endereço da base a menos disso de uma UC da planilha = o próprio endereço dela


def amostra_separada(e: gpd.GeoDataFrame) -> pd.DataFrame:
    teste = np.random.default_rng(C.SEMENTE).random(len(e)) < FRACAO_TESTE
    b = BT.base(e, ~teste)
    t = e[teste & ~e["REATRIBUIDO"].astype(bool).to_numpy()]
    prev, _, _ = comunidade_de(np.c_[t.geometry.x, t.geometry.y], b)
    acerto = _chave_nome(pd.Series(prev, index=t.index)) == _chave_nome(t["COMUNIDADE"])
    return acerto.groupby(t["ZONA"]).agg(["mean", "size"]).rename(columns={"mean": "ACERTO", "size": "ENDERECOS"})


def localizar_por_partes(e: gpd.GeoDataFrame, xy_uc: np.ndarray) -> pd.DataFrame:
    """Cada UC localizada com uma base que não tem o próprio endereço: os endereços são divididos
    em PARTES por sorteio fixo, e a UC usa a base montada sem a parte do endereço dela (e sem
    nenhum endereço no mesmo ponto de uma UC dessa parte). Os vizinhos continuam na base."""
    xy_end = np.c_[e.geometry.x, e.geometry.y]
    arvore = KDTree(xy_end)
    parte_end = np.random.default_rng(C.SEMENTE).integers(0, PARTES, len(e))
    parte_uc = parte_end[arvore.query(xy_uc, k=1)[1][:, 0]]  # a parte do endereço no mesmo ponto
    limite, partes = BT.contorno(), []
    for k in range(PARTES):
        pos = np.where(parte_uc == k)[0]
        usar = parte_end != k
        usar[np.concatenate(arvore.query_radius(xy_uc[pos], r=RAIO_MESMO_ENDERECO_M))] = False
        partes.append(localizar(xy_uc[pos], [BT.base(e, usar, limite)]).set_index(pos))
    return pd.concat(partes).sort_index()


def planilhas_de_teste(e: gpd.GeoDataFrame, regras) -> pd.DataFrame:
    ucs = gpd.read_file(C.SINTETICO / "ucs.gpkg", columns=["UC", "CHAVES_MONTANTE"], ignore_geometry=True)
    gab = pd.read_csv(C.SINTETICO / "gabarito_uc.csv", dtype={"UC": str})
    u = ucs.merge(gab[["UC", "COMUNIDADE", "ZONA", "LAT_REAL", "LON_REAL"]], on="UC").reset_index(drop=True)
    p = gpd.GeoSeries(gpd.points_from_xy(u["LON_REAL"], u["LAT_REAL"]), crs=C.CRS_GEO).to_crs(BT.CRS_BASE)
    loc = localizar_por_partes(e, np.c_[p.x, p.y])
    reais = set(_chave_nome(u["COMUNIDADE"]))
    real_uc = _chave_nome(u["COMUNIDADE"]).to_numpy()
    loc["PREVISTO_NORM"] = _alinhar(_chave_nome(loc["COMUNIDADE_PREVISTA"].fillna("")), reais)
    bases = [BT.base(e)]  # no aviso, o tamanho de cada comunidade vem da base inteira
    linhas = []
    for cod in gpd.read_file(C.SINTETICO / "chaves.gpkg", columns=["COD_CHAVE"], ignore_geometry=True)["COD_CHAVE"]:
        af = ucs_afetadas(u, cod)
        if af.empty:
            continue
        r = avisar(loc.loc[af.index], bases, regras)
        m = r.municipios[0]
        prev = loc.loc[m.ucs.index, "PREVISTO_NORM"].to_numpy()
        citadas = m.comunidades.loc[~m.comunidades["FRAGMENTO"], "COMUNIDADE_PREVISTA"]
        conj_r = set(real_uc[af.index])
        conj_p = set(prev[m.ucs["COMUNIDADE_PREVISTA"].isin(citadas).to_numpy()])
        inter = len(conj_r & conj_p)
        linhas.append({"CHAVE": cod, "UCS": len(af), "FORA": len(r.fora), "RURAL": (af["ZONA"] == "Rural").mean(),
                       "PRECISAO": inter / len(conj_p), "COBERTURA": inter / len(conj_r),
                       "COBERTURA_UC": float(np.isin(real_uc[af.index], list(conj_p)).mean()),
                       "ACERTO_UC": float((prev == real_uc[m.ucs.index]).mean()), "SEG_DEPOIS": m.segundos})
    return pd.DataFrame(linhas)


def _medias(c: pd.DataFrame) -> dict:
    return {"cobertura": c["COBERTURA"].mean() * 100, "cobertura por UC": c["COBERTURA_UC"].mean() * 100,
            "precisão": c["PRECISAO"].mean() * 100, "aviso (s)": c["SEG_DEPOIS"].mean()}


if __name__ == "__main__":
    dist = dist_.carregar()
    e = BT.enderecos()
    print(f"Base territorial: {len(e)} endereços, {e['COMUNIDADE'].nunique()} comunidades ({C.NOME_MUNICIPIO}/{C.UF})")
    a = amostra_separada(e)
    print(f"\n== 1. Amostra separada ({FRACAO_TESTE:.0%} dos endereços fora da base; só rótulos originais) ==")
    print((a.assign(ACERTO=(a["ACERTO"] * 100).round(1))).to_string())

    cen = planilhas_de_teste(e, dist.regras)
    cen.to_csv(C.SAIDA / "avaliacao_planilha.csv", index=False)
    antes = pd.read_csv(C.SAIDA / "avaliacao_cenarios.csv").set_index("CHAVE").reindex(cen["CHAVE"]).reset_index()
    print(f"\n== 2. Planilhas de teste: {len(cen)} chaves, UCs fora do município: {int(cen['FORA'].sum())} ==")
    print(f"Acerto por UC (planilha): {cen['ACERTO_UC'].mean() * 100:.1f}%")
    for nome, filtro in {"todas": slice(None), "rurais (>=80% rural)": cen["RURAL"] >= 0.8}.items():
        t = pd.DataFrame({"algoritmo atual (cadastro digitado)": _medias(antes[filtro]),
                          "planilha (só coordenada)": _medias(cen[filtro])}).round(1)
        print(f"\n-- {nome} ({len(cen[filtro])} chaves) --")
        print(t.to_string())
