"""Janela de menor dano e cargas sensíveis de um desligamento.

Puro: recebe a contagem de UCs afetadas por atividade (nunca nomes), os perfis e o
expediente (vindos da configuração da distribuidora) e devolve notas e sugestões.
É uma sugestão para a equipe, que continua decidindo. Os perfis são hipóteses.

Tempos em minutos desde a meia-noite. A nota é inteira (quantidade × peso × minutos),
para o navegador reproduzir exatamente o mesmo resultado.
"""

from datetime import date

from . import perfis_carga as P
from .perfis_carga import Expediente

SLOT_MIN = 30                  # granularidade dos pesos ao longo do dia
SLOTS = 24 * 60 // SLOT_MIN    # meias horas do dia


def tipo_dia(d: date) -> str:
    return P.UTIL if d.weekday() < 5 else P.SABADO if d.weekday() == 5 else P.DOMINGO


def _min(h: float) -> int:
    return round(h * 60)


def _sobreposicao(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def pesos(perfil: P.Perfil, tipo: str) -> list[int]:
    """Nível de sensibilidade de cada meia hora do dia (o maior entre o padrão e os períodos)."""
    w = []
    for s in range(SLOTS):
        ini = s * SLOT_MIN
        nivel = perfil.padrao[tipo]
        for p in perfil.periodos:
            if tipo in p.dias and _min(p.inicio_h) <= ini < _min(p.fim_h):
                nivel = max(nivel, p.nivel)
        w.append(nivel)
    return w


def _nota(contagem: dict, tipo: str, inicio: int, duracao: int, perfis: dict) -> int:
    fim, total = inicio + duracao, 0
    for atividade, perfil in perfis.items():
        n = contagem.get(atividade, 0)
        if not n:
            continue
        w = pesos(perfil, tipo)
        for s in range(SLOTS):
            o = _sobreposicao(inicio, fim, s * SLOT_MIN, (s + 1) * SLOT_MIN)
            if o:
                total += n * w[s] * o
    return total


def nota_dano(contagem: dict, data: date, inicio: int, duracao: int, perfis: dict) -> int:
    """Soma, por atividade, quantidade × peso × minutos de cada meia hora dentro da janela."""
    return _nota(contagem, tipo_dia(data), inicio, duracao, perfis)


def inicios_possiveis(duracao: int, exp: Expediente) -> list[int]:
    if duracao <= 0:
        return []
    ultimo = min(exp.ultimo_inicio, exp.fim - duracao)
    return list(range(exp.inicio, ultimo + 1, exp.passo))


def _lista(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _qtd(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def explicar(contagem: dict, tipo: str, inicio: int, fim: int, perfis: dict, exp: Expediente) -> str:
    """Uma linha: os maiores conflitos da janela e os horários de peso alto que ela evita."""
    conflitos, evitados = [], []
    for atividade, perfil in perfis.items():
        n = contagem.get(atividade, 0)
        if not n:
            continue
        for p in perfil.periodos:
            if tipo not in p.dias:
                continue
            p0, p1 = _min(p.inicio_h), _min(p.fim_h)
            o = _sobreposicao(inicio, fim, p0, p1)
            if o and p.nivel >= P.MEDIO:
                rotulo = perfil.singular if n == 1 else perfil.plural
                conflitos.append((n * p.nivel * o, len(conflitos), f"{p.nome} de {_qtd(n)} {rotulo}"))
            elif not o and p.nivel == P.ALTO and _sobreposicao(exp.inicio, exp.fim, p0, p1):
                evitados.append(p.nome)
    conflitos.sort(key=lambda c: (-c[0], c[1]))
    pega = [c[2] for c in conflitos[:2]]
    if pega:
        return f"Pega {_lista(pega)}" + (f"; evita {_lista(evitados)}" if evitados else "")
    if evitados:
        return f"Evita {_lista(evitados)}"
    if _nota(contagem, tipo, inicio, fim - inicio, perfis):
        return "Só atinge horários de baixa sensibilidade"
    return "Sem conflito com os horários sensíveis"


def avaliar_janelas(contagem: dict, data: date, duracao: int, perfis: dict, exp: Expediente) -> list[dict]:
    """Todas as janelas do expediente, da menor para a maior nota (empate: a que começa antes)."""
    tipo = tipo_dia(data)
    js = [{"inicio": i, "fim": i + duracao, "nota": _nota(contagem, tipo, i, duracao, perfis)}
          for i in inicios_possiveis(duracao, exp)]
    js.sort(key=lambda j: (j["nota"], j["inicio"]))
    for j in js:
        j["tipo"] = tipo
    return js


def sugerir_janelas(contagem: dict, data: date, duracao: int, perfis: dict, exp: Expediente,
                    quantas: int = 3) -> list[dict]:
    melhores = avaliar_janelas(contagem, data, duracao, perfis, exp)[:quantas]
    for j in melhores:
        j["explicacao"] = explicar(contagem, j["tipo"], j["inicio"], j["fim"], perfis, exp)
    return melhores


def cargas_sensiveis(contagem: dict) -> dict:
    """Quantas unidades de saúde, escolas e estabelecimentos agropecuários há na área (só contagens)."""
    return {a: int(contagem.get(a, 0)) for a in P.SENSIVEIS}


def perfis_para_mapa(perfis: dict, exp: Expediente, razao_muito_pior: float) -> dict:
    """Perfis e expediente no formato que o navegador usa para repetir o mesmo cálculo."""
    return {
        "atividades": list(perfis),
        "pesos": {a: {t: pesos(p, t) for t in P.TIPOS_DIA} for a, p in perfis.items()},
        "periodos": {a: [[q.nome, list(q.dias), _min(q.inicio_h), _min(q.fim_h), q.nivel] for q in p.periodos]
                     for a, p in perfis.items()},
        "rotulos": {a: [p.singular, p.plural] for a, p in perfis.items()},
        "sensiveis": list(P.SENSIVEIS),
        "niveis": {"medio": P.MEDIO, "alto": P.ALTO},
        "slot": SLOT_MIN,
        "expediente": {"inicio": exp.inicio, "ultimoInicio": exp.ultimo_inicio, "fim": exp.fim, "passo": exp.passo},
        "razaoMuitoPior": razao_muito_pior,
    }
