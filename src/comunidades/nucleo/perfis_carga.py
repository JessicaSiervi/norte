"""Tipos dos perfis de sensibilidade e do expediente (puro: não lê arquivos).

Os valores ficam na configuração da distribuidora (distribuidoras/*.toml), que o
pipeline lê e entrega aqui já como dicionário. Os perfis são hipóteses de
demonstração, a validar com a distribuidora e por região.
"""

from dataclasses import dataclass

# Níveis de sensibilidade (inteiros, para o navegador e o Python darem o mesmo resultado)
ZERO, BAIXO, MEDIO, ALTO = 0, 1, 2, 3
NIVEIS = {"ZERO": ZERO, "BAIXO": BAIXO, "MEDIO": MEDIO, "ALTO": ALTO}

UTIL, SABADO, DOMINGO = "util", "sabado", "domingo"
TIPOS_DIA = (UTIL, SABADO, DOMINGO)

# Atividades que contam como carga sensível no alerta (regra do produto, não da distribuidora)
SENSIVEIS = ("saude", "ensino", "agropecuaria")


@dataclass(frozen=True)
class Periodo:
    nome: str          # como aparece na explicação ("a ordenha da tarde")
    dias: tuple        # tipos de dia em que vale
    inicio_h: float    # hora de início (inclusive)
    fim_h: float       # hora de fim (exclusive)
    nivel: int


@dataclass(frozen=True)
class Perfil:
    singular: str
    plural: str
    padrao: dict       # nível fora dos períodos, por tipo de dia
    periodos: tuple = ()


@dataclass(frozen=True)
class Expediente:
    inicio: int        # minutos desde a meia-noite: primeiro início possível
    ultimo_inicio: int
    fim: int           # a obra termina até aqui
    passo: int


def perfis_de_dict(d: dict) -> dict:
    """{atividade: {singular, plural, padrao, periodos}} -> {atividade: Perfil}, na ordem recebida."""
    return {
        atividade: Perfil(
            p["singular"], p["plural"], {t: NIVEIS[p["padrao"][t]] for t in TIPOS_DIA},
            tuple(Periodo(q["nome"], tuple(q["dias"]), q["inicio_h"], q["fim_h"], NIVEIS[q["nivel"]])
                  for q in p["periodos"]))
        for atividade, p in d.items()
    }


def expediente_de_dict(d: dict) -> Expediente:
    return Expediente(round(d["inicio_min_h"] * 60), round(d["ultimo_inicio_h"] * 60),
                      round(d["fim_max_h"] * 60), int(d["passo_min"]))
