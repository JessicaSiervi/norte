"""Teste de robustez: quanto as métricas dependem das escolhas da simulação.

Roda o cadastro fictício e o algoritmo com variações (semente do cadastro, ruído
no campo de localidade, peso do transformador na votação), uma por vez, e avalia
cada uma. No fim restaura tudo ao estado base, para que saida/ e data/sintetico/
fiquem iguais ao pipeline oficial. O mapa não é regenerado aqui.

Uso: py -m uv run python -m comunidades.validacao.robustez
"""

import time

import pandas as pd

from .. import config as C
from ..nucleo import algoritmo
from ..pipeline import rodar_algoritmo
from ..simulacao import clientes
from .avaliacao import avaliar

PESO_BASE = algoritmo.PESO_MESMO_TRAFO
SEMENTES_EXTRA = [1, 2, 3]

# (nome, semente do cadastro, fator de ruído, peso do mesmo trafo)
VARIACOES = (
    [("a. base", C.SEMENTE, 1.0, PESO_BASE),
     ("b. sem peso do trafo", C.SEMENTE, 1.0, 1.0)]
    + [(f"c. semente {s}", s, 1.0, PESO_BASE) for s in SEMENTES_EXTRA]
    + [("d. ruído x1.5", C.SEMENTE, 1.5, PESO_BASE),
       ("e. ruído x1.5 sem peso do trafo", C.SEMENTE, 1.5, 1.0)]
)

COLUNAS = ["ACERTO_CADASTRO_RURAL", "ACERTO_RURAL", "ACERTO_URBANO", "PRECISAO", "COBERTURA", "COBERTURA_UC"]


def _rodar(semente: int, fator: float, peso: float, cadastro_atual: tuple | None) -> dict:
    if cadastro_atual != (semente, fator):  # só regenera o cadastro quando ele muda
        clientes.construir(semente=semente, fator_ruido=fator)
    algoritmo.PESO_MESMO_TRAFO = peso
    rodar_algoritmo()
    _, por_uc, _, cen = avaliar()
    return {
        "ACERTO_CADASTRO_RURAL": por_uc.loc["Rural", "ACERTO_CADASTRO"],
        "ACERTO_RURAL": por_uc.loc["Rural", "ACERTO"],
        "ACERTO_URBANO": por_uc.loc["Urbana", "ACERTO"],
        "PRECISAO": cen["PRECISAO"].mean(),
        "COBERTURA": cen["COBERTURA"].mean(),
        "COBERTURA_UC": cen["COBERTURA_UC"].mean(),
    }


def restaurar():
    """Volta ao estado do pipeline oficial: cadastro e algoritmo com os valores originais."""
    algoritmo.PESO_MESMO_TRAFO = PESO_BASE
    clientes.construir()
    rodar_algoritmo()
    avaliar()  # regrava saida/avaliacao_cenarios.csv


def executar() -> pd.DataFrame:
    linhas, cadastro = [], None
    try:
        for nome, semente, fator, peso in VARIACOES:
            t0 = time.perf_counter()
            print(f"> {nome}...", flush=True)
            r = _rodar(semente, fator, peso, cadastro)
            cadastro = (semente, fator)
            linhas.append({"VARIACAO": nome, "SEMENTE": semente, "FATOR_RUIDO": fator, "PESO_TRAFO": peso,
                           **r, "SEGUNDOS": round(time.perf_counter() - t0)})
    finally:
        print("> Restaurando o estado base...", flush=True)
        restaurar()
    tab = pd.DataFrame(linhas)
    tab.to_csv(C.SAIDA / "robustez.csv", index=False)
    return tab


if __name__ == "__main__":
    t0 = time.perf_counter()
    tab = executar()
    print("\n== Robustez: uma linha por variação ==")
    print(tab.set_index("VARIACAO")[["SEMENTE", "FATOR_RUIDO", "PESO_TRAFO"] + COLUNAS].round(3).to_string())
    sem = tab[tab["VARIACAO"].str.startswith("c.")][COLUNAS]
    print(f"\n== Sementes do cadastro {SEMENTES_EXTRA}: média e variação ==")
    print(pd.DataFrame({"média": sem.mean(), "mínimo": sem.min(), "máximo": sem.max()}).T.round(3).to_string())
    print(f"\nTempo total: {time.perf_counter() - t0:.0f} s (inclui a restauração)")
    print(f"Tabela: {C.SAIDA / 'robustez.csv'}")
