"""Avaliação contra o gabarito do IBGE (CNEFE 2022): por UC e por cenário de desligamento."""

import geopandas as gpd
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from .. import config as C
from .. import distribuidora as dist_
from ..nucleo.desligamento import _sem_sufixo, duracao_s, simular
from ..nucleo.nomes import normalizar


def _chave_nome(s: pd.Series) -> pd.Series:
    return s.map(lambda n: normalizar(_sem_sufixo(str(n))))


def _alinhar(previstos: pd.Series, reais: set) -> pd.Series:
    """Nome previsto -> grafia do gabarito quando são variantes (ex.: CAICARA x CAICARAS)."""
    def f(n):
        m = process.extractOne(n, reais, scorer=fuzz.ratio)
        return m[0] if m and m[1] >= 90 else n
    mapa = {n: f(n) for n in previstos.unique()}
    return previstos.map(mapa)


def avaliar(dist=None):
    """dist: configuração da distribuidora (padrão: distribuidoras/demo-leopoldina.toml)."""
    dist = dist or dist_.carregar()
    g = gpd.read_file(C.SAIDA / "ucs_comunidade.gpkg")
    gab = pd.read_csv(C.SINTETICO / "gabarito_uc.csv", dtype={"UC": str})
    df = g.merge(gab[["UC", "COMUNIDADE", "ZONA", "RUIDO_LOCALIDADE", "RUIDO_COORD"]], on="UC")
    real = _chave_nome(df["COMUNIDADE"])
    df["PREVISTO_NORM"] = _alinhar(_chave_nome(df["COMUNIDADE_PREVISTA"]), set(real))
    df["ACERTO"] = df["PREVISTO_NORM"] == real
    df["ACERTO_CADASTRO"] = df["BAIRRO_LOCALIDADE"].map(normalizar) == real  # baseline: confiar no campo digitado

    por_uc = df.groupby("ZONA")[["ACERTO_CADASTRO", "ACERTO"]].mean().round(3)
    por_ruido = df[df.ZONA == "Rural"].groupby("RUIDO_LOCALIDADE")["ACERTO"].mean().round(3)

    # Cenários: uma chave aberta por vez
    ch = gpd.read_file(C.SINTETICO / "chaves.gpkg")
    linhas = []
    for cod in ch["COD_CHAVE"]:
        d = simular(df, cod, dist.regras)
        if d.ucs.empty:
            continue
        real_uc = _chave_nome(d.ucs["COMUNIDADE"])
        r = set(real_uc)
        # Só conta o que o aviso cita pelo nome (fragmentos viram "localidades vizinhas")
        citadas = d.comunidades.loc[~d.comunidades["FRAGMENTO"], "COMUNIDADE_PREVISTA"]
        p = set(d.ucs.loc[d.ucs["COMUNIDADE_PREVISTA"].isin(citadas), "PREVISTO_NORM"])
        inter = len(r & p)
        linhas.append({
            "CHAVE": cod, "UCS": len(d.ucs), "RURAL": (d.ucs["ZONA"] == "Rural").mean(),
            "N_REAL": len(r), "N_PREV": len(p),
            "PRECISAO": inter / len(p), "COBERTURA": inter / len(r), "EXATO": r == p,
            # parcela das UCs desligadas cuja comunidade real é citada pelo nome no aviso
            "COBERTURA_UC": real_uc.isin(p).mean(),
            "SEG_ANTES": duracao_s(d.aviso_antigo), "SEG_DEPOIS": duracao_s(d.aviso_novo),
        })
    cen = pd.DataFrame(linhas)
    cen.to_csv(C.SAIDA / "avaliacao_cenarios.csv", index=False)
    return df, por_uc, por_ruido, cen


if __name__ == "__main__":
    df, por_uc, por_ruido, cen = avaliar()
    print("== Acerto por UC (cadastro digitado x algoritmo) ==")
    print(por_uc)
    print("\n== Acerto rural por tipo de ruído no cadastro ==")
    print(por_ruido)
    for nome, c in {"todos": cen, "rurais (>=80% rural)": cen[cen.RURAL >= 0.8]}.items():
        print(f"\n== Cenários de desligamento: {nome} ({len(c)}) ==")
        print(c[["UCS", "N_REAL", "N_PREV", "PRECISAO", "COBERTURA", "COBERTURA_UC", "EXATO", "SEG_ANTES", "SEG_DEPOIS"]]
              .describe().loc[["mean", "50%", "max"]].round(2).to_string())
    erros = df[(df.ZONA == "Rural") & ~df.ACERTO]
    print("\n== Confusões rurais mais comuns (real -> previsto) ==")
    print((erros["COMUNIDADE"] + "  ->  " + erros["COMUNIDADE_PREVISTA"]).value_counts().head(20).to_string())
