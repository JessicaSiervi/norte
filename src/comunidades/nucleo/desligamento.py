"""Simulação de desligamento programado e geração do aviso de rádio (antes x depois).

Puro: limites, município e assinatura vêm da configuração da distribuidora (RegrasAviso),
e o texto do aviso vem dos modelos por idioma (idiomas.py).
"""

import re
from dataclasses import dataclass, field

import pandas as pd

from . import idiomas

# Locução de rádio ~150 palavras/min. É uma aproximação, usada para todos os idiomas.
PALAVRAS_POR_SEGUNDO = 2.5


@dataclass(frozen=True)
class RegrasAviso:
    limiar_total: float          # >= esta fração das UCs da comunidade afetadas -> comunidade inteira
    # Comunidade atingida só em parte, com poucas UCs afetadas e pouco peso no ramal, é quase
    # sempre ruído da votação na fronteira (fragmento). Ela não é citada pelo nome: o aviso diz
    # "além de localidades vizinhas", para que essas poucas UCs não fiquem sem aviso.
    limite_fragmento: int        # até tantas UCs afetadas...
    limite_participacao: float   # ...e menos desta fração das UCs desligadas pela chave
    municipio: str               # citado no aviso; o distrito com este nome vira "Sede"
    assinatura_aviso_atual: str  # quem assina o aviso de hoje ("A Energisa informa...")


@dataclass
class Desligamento:
    chave: str
    ucs: pd.DataFrame                    # UCs afetadas (com COMUNIDADE_PREVISTA)
    comunidades: pd.DataFrame = field(default=None)
    aviso_antigo: str = ""
    aviso_novo: str = ""


def ucs_afetadas(ucs: pd.DataFrame, chave: str) -> pd.DataFrame:
    alvo = ucs["CHAVES_MONTANTE"].fillna("").str.contains(rf"(?:^|;){re.escape(chave)}(?:;|$)")
    return ucs[alvo]


def _sem_sufixo(nome: str) -> str:
    return re.sub(r" \(.*\)$", "", nome)


def resumir(afetadas: pd.DataFrame, todas: pd.DataFrame, regras: RegrasAviso) -> pd.DataFrame:
    return resumir_por_total(afetadas, todas["COMUNIDADE_PREVISTA"].value_counts(), regras)


def resumir_por_total(afetadas: pd.DataFrame, total: pd.Series, regras: RegrasAviso) -> pd.DataFrame:
    """Como resumir, com o tamanho de cada comunidade já contado (total: comunidade -> unidades).
    Na planilha de UCs afetadas o total vem da base territorial, e não das próprias UCs."""
    c = afetadas.groupby("COMUNIDADE_PREVISTA").agg(
        UC_AFETADAS=("UC", "count"), CONFIANCA=("CONFIANCA", "mean"), DISTRITO=("DISTRITO", lambda s: s.mode().iat[0])
    )
    c["UC_TOTAL"] = total.reindex(c.index).to_numpy()
    c["PARCIAL"] = c["UC_AFETADAS"] / c["UC_TOTAL"] < regras.limiar_total
    # estável: no empate, fica a ordem alfabética do groupby (o navegador repete a mesma ordem)
    c = c.sort_values("UC_AFETADAS", ascending=False, kind="stable").reset_index()
    c["FRAGMENTO"] = (c["PARCIAL"] & (c["UC_AFETADAS"] <= regras.limite_fragmento)
                      & (c["UC_AFETADAS"] / c["UC_AFETADAS"].sum() < regras.limite_participacao))
    if len(c) and c["FRAGMENTO"].all():  # ramal minúsculo: cita ao menos a comunidade maior
        c.loc[0, "FRAGMENTO"] = False
    return c


def _local_bruto(ucs: pd.DataFrame) -> pd.Series:
    """O local de cada UC no aviso de hoje, como está no cadastro: o imóvel, senão o logradouro."""
    return ucs["NOME_IMOVEL"].where(ucs["NOME_IMOVEL"].fillna("") != "", ucs["LOGRADOURO"])


def locais_antigos(afetadas: pd.DataFrame) -> list[str]:
    """Como o sistema cita hoje: o imóvel (rural) ou a rua (urbano) de cada UC, sem repetir."""
    return locais_de(_local_bruto(afetadas))


def locais_de(locais: pd.Series) -> list[str]:
    """O local de cada UC (imóvel ou rua, como no cadastro; None = sem local) -> os locais citados, sem repetir, na ordem."""
    return [l.title() for l in pd.unique(locais.dropna())]


# Começo fixo do aviso de hoje (antes da lista de locais); o mapa recebe o mesmo modelo
CABECALHO_ANTIGO = ("Atenção! A {assinatura} informa desligamento programado no dia {data}, "
                    "das {horario}, para manutenção na rede elétrica, atingindo: ")


def aviso_antigo(afetadas: pd.DataFrame, data: str, horario: str, regras: RegrasAviso) -> str:
    """O aviso como é hoje (em português): imóvel por imóvel (rural) e rua por rua (urbano)."""
    return aviso_antigo_de_locais(_local_bruto(afetadas), data, horario, regras)


def aviso_antigo_de_locais(locais: pd.Series, data: str, horario: str, regras: RegrasAviso) -> str:
    """O aviso de hoje a partir do local de cada UC (a coluna local da planilha, ou o cadastro)."""
    return (CABECALHO_ANTIGO.format(assinatura=regras.assinatura_aviso_atual, data=data, horario=horario)
            + f"{idiomas.lista(locais_de(locais), 'pt-BR')}.")


def codigos_locais(ucs: pd.DataFrame) -> tuple[list[int], list[int]]:
    """Local de cada UC no aviso de hoje como código (-1 = não entra) e as palavras de cada local.

    O código segue a ordem em que o local aparece no cadastro (não a alfabética), e a repetição é
    decidida pelo texto do cadastro, como em locais_antigos. Os nomes não saem daqui."""
    codigos, unicos = pd.factorize(_local_bruto(ucs))
    return [int(c) for c in codigos], [len(l.title().split()) for l in unicos]


def palavras_do_e() -> int:
    """Palavras de ligação antes do último local ("A, B e C"): o mesmo número com ou sem som de "i"."""
    m = idiomas.IDIOMAS["pt-BR"]
    if len(m["e"].split()) != len(m["e_antes_de_i"].split()):
        raise ValueError("O tamanho do aviso de hoje supõe a mesma ligação antes do último local.")
    return len(m["e"].split())


def tamanho_aviso_antigo(codigos, palavras_por_local: list[int], data: str, horario: str,
                         regras: RegrasAviso) -> tuple[int, int, int]:
    """Locais citados, palavras e segundos no ar do aviso de hoje, sem montar o texto.

    Mesmas regras de aviso_antigo: locais sem repetição, o começo fixo com a data e o horário e
    a ligação da lista. Sem nenhum local o texto termina em "atingindo: .", e o ponto conta."""
    locais = {c for c in codigos if c >= 0}
    cab = CABECALHO_ANTIGO.format(assinatura=regras.assinatura_aviso_atual, data=data, horario=horario)
    n = len(cab.split()) + sum(palavras_por_local[c] for c in locais)
    if len(locais) >= 2:
        n += palavras_do_e()
    elif not locais:
        n += 1  # o "." sozinho
    return len(locais), n, round(n / PALAVRAS_POR_SEGUNDO)


def partes_do_aviso(resumo: pd.DataFrame, municipio: str) -> tuple:
    """Inteiras, parciais, se há vizinhas e os distritos, já decididos pelas regras do produto."""
    citadas = resumo[~resumo["FRAGMENTO"]]
    nomes = citadas["COMUNIDADE_PREVISTA"].map(_sem_sufixo)
    inteiras = list(dict.fromkeys(nomes[~citadas["PARCIAL"]]))
    parciais = [n for n in dict.fromkeys(nomes[citadas["PARCIAL"]]) if n not in inteiras]
    distritos = sorted({"Sede" if d == municipio else d for d in resumo["DISTRITO"]})
    return inteiras, parciais, bool(resumo["FRAGMENTO"].any()), distritos


def aviso_novo(resumo: pd.DataFrame, data: str, horario: str, regras: RegrasAviso,
               idioma: str = idiomas.PADRAO) -> str:
    inteiras, parciais, vizinhas, distritos = partes_do_aviso(resumo, regras.municipio)
    return idiomas.montar(inteiras, parciais, vizinhas, distritos, regras.municipio, data, horario, idioma)


def duracao_s(texto: str) -> float:
    return len(texto.split()) / PALAVRAS_POR_SEGUNDO


def simular(ucs: pd.DataFrame, chave: str, regras: RegrasAviso, data="12/11", horario="8h às 14h") -> Desligamento:
    afet = ucs_afetadas(ucs, chave)
    d = Desligamento(chave=chave, ucs=afet)
    d.comunidades = resumir(afet, ucs, regras)
    d.aviso_antigo = aviso_antigo(afet, data, horario, regras)
    d.aviso_novo = aviso_novo(d.comunidades, data, horario, regras)
    return d
