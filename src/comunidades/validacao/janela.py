"""Janela de menor dano nos ramais rurais: quanto a sugestão reduz a nota de dano.

Compara, num dia útil, o horário padrão suposto (começando às 8h) com a janela sugerida
de mesma duração, e mede a diferença entre a pior e a melhor janela do expediente.
Roda com dois perfis lado a lado: o anterior (sem o resfriamento do leite) e o atual.
O resultado depende inteiramente dos perfis hipotéticos da configuração da distribuidora ativa
(distribuidoras/demo-leopoldina.toml por padrão).

Uso: py -m uv run python -m comunidades.validacao.janela
"""

from dataclasses import replace
from datetime import date

import pandas as pd

from .. import config as C
from .. import distribuidora as dist_
from ..nucleo.desligamento import simular
from ..nucleo.impacto import avaliar_janelas, nota_dano, tipo_dia
from .avaliacao import avaliar

DATA = date(2026, 11, 12)          # quinta-feira (dia útil), a data padrão do aviso
INICIO_PADRAO = 8 * 60             # suposição nossa: hoje a obra começa às 8h
DURACOES_H = (2, 4, 6)             # 6 h = 8h às 14h, o horário padrão do aviso
LIMIAR_RURAL = 0.8

VERSOES = ("sem resfriamento", "com resfriamento")


def versoes_dos_perfis(perfis: dict) -> dict:
    """Perfil anterior (o atual sem os períodos de resfriamento do leite) e o atual, para comparação."""
    agro = perfis["agropecuaria"]
    anterior = {**perfis, "agropecuaria": replace(
        agro, periodos=tuple(p for p in agro.periodos if "resfriamento" not in p.nome))}
    return dict(zip(VERSOES, (anterior, perfis)))


def _hora(m: int) -> str:
    return f"{m // 60}h" + (f"{m % 60:02d}" if m % 60 else "")


def calcular(dist=None) -> pd.DataFrame:
    dist = dist or dist_.carregar()
    atividades, versoes = list(dist.perfis), versoes_dos_perfis(dist.perfis)
    df, _, _, cen = avaliar(dist)
    linhas = []
    for cod in cen.loc[cen["RURAL"] >= LIMIAR_RURAL, "CHAVE"]:
        d = simular(df, cod, dist.regras)
        cont = d.ucs["ATIVIDADE"].value_counts().reindex(atividades, fill_value=0).astype(int).to_dict()
        for versao, perfis in versoes.items():
            for h in DURACOES_H:
                js = avaliar_janelas(cont, DATA, h * 60, perfis, dist.expediente)
                linhas.append({
                    "PERFIL": versao, "CHAVE": cod, "UCS": len(d.ucs), "SAUDE": cont["saude"],
                    "ENSINO": cont["ensino"], "AGROPECUARIA": cont["agropecuaria"], "DURACAO_H": h,
                    "NOTA_PADRAO": nota_dano(cont, DATA, INICIO_PADRAO, h * 60, perfis),
                    "MELHOR_INICIO": js[0]["inicio"], "NOTA_MELHOR": js[0]["nota"],
                    "PIOR_INICIO": js[-1]["inicio"], "NOTA_PIOR": js[-1]["nota"],
                })
    t = pd.DataFrame(linhas)
    t["REDUCAO"] = (1 - t["NOTA_MELHOR"] / t["NOTA_PADRAO"]).where(t["NOTA_PADRAO"] > 0)
    t["RAZAO_PIOR_MELHOR"] = (t["NOTA_PIOR"] / t["NOTA_MELHOR"]).where(t["NOTA_MELHOR"] > 0)
    t.to_csv(C.SAIDA / "janela_ramais.csv", index=False)
    return t


def _lado_a_lado(t: pd.DataFrame, metricas) -> pd.DataFrame:
    """Uma linha por métrica e duração; uma coluna por versão do perfil."""
    linhas = []
    for nome, f in metricas:
        for h in DURACOES_H:
            linha = {"métrica": nome, "duração": f"{h} h"}
            for versao in VERSOES:
                linha[versao] = f(t[(t["DURACAO_H"] == h) & (t["PERFIL"] == versao)])
            linhas.append(linha)
    return pd.DataFrame(linhas)


def _pct(v) -> str:
    return "-" if pd.isna(v) else f"{v:.1%}"


if __name__ == "__main__":
    t = calcular()
    ramais = t[(t["DURACAO_H"] == DURACOES_H[0]) & (t["PERFIL"] == "com resfriamento")]
    n = len(ramais)
    print(f"== Janela de menor dano · {n} ramais rurais (>= {LIMIAR_RURAL:.0%} rural) · "
          f"dia útil ({DATA:%d/%m/%Y}, tipo '{tipo_dia(DATA)}') ==")
    print(f"ATENÇÃO: os perfis de sensibilidade são HIPÓTESES de demonstração (distribuidoras/{C.ARQ_DISTRIBUIDORA.name}),")
    print("a validar com a distribuidora e por região. O 'horário padrão' (começar às 8h: 8h às 14h para 6 h,")
    print("8h às 12h para 4 h e 8h às 10h para 2 h) é uma SUPOSIÇÃO NOSSA, não o horário real da distribuidora.")
    print("Perfis comparados: 'sem resfriamento' (anterior) e 'com resfriamento' (atual: + resfriamento do leite")
    print("das 7h às 10h e das 17h às 20h, IN 77/2018 do MAPA). Nada mais muda entre eles.\n")

    saude, ensino = (ramais["SAUDE"] > 0).sum(), (ramais["ENSINO"] > 0).sum()
    ambos = ((ramais["SAUDE"] > 0) | (ramais["ENSINO"] > 0)).sum()
    print(f"Ramais com pelo menos 1 unidade de saúde ou escola: {ambos} de {n} "
          f"(com saúde: {saude}; com escola: {ensino})\n")

    pd.set_option("display.width", 250)
    print("== Padrão (início às 8h) x janela sugerida de mesma duração ==")
    print(_lado_a_lado(t, [
        ("redução média", lambda g: _pct(g["REDUCAO"].mean())),
        ("redução mediana", lambda g: _pct(g["REDUCAO"].median())),
        ("(a) padrão não é o melhor", lambda g: f"{(g['NOTA_MELHOR'] < g['NOTA_PADRAO']).sum()} de {len(g)}"),
        ("(a) redução média nesses", lambda g: _pct(g.loc[g["NOTA_MELHOR"] < g["NOTA_PADRAO"], "REDUCAO"].mean())),
    ]).to_string(index=False))

    print("\n== (c) Pior x melhor janela do expediente ==")
    print(_lado_a_lado(t, [
        ("razão média pior/melhor", lambda g: f"{g['RAZAO_PIOR_MELHOR'].mean():.2f}"),
        ("razão mediana", lambda g: f"{g['RAZAO_PIOR_MELHOR'].median():.2f}"),
        ("pior >= 2x melhor", lambda g: f"{(g['RAZAO_PIOR_MELHOR'] >= 2).sum()} de {g['RAZAO_PIOR_MELHOR'].notna().sum()}"),
        ("melhor com nota zero", lambda g: int((g["NOTA_MELHOR"] == 0).sum())),
    ]).to_string(index=False))
    print(f"\nTabela por ramal (as duas versões): {C.SAIDA / 'janela_ramais.csv'}")
