"""UCs afetadas vindas da planilha da distribuidora: município, comunidade e aviso de cada município.

Puro: recebe as coordenadas das UCs (já projetadas em metros) e a base territorial de cada
município (contorno e endereços de referência com a comunidade e o distrito) e devolve o
resultado. Quem chama lê a planilha e os arquivos, projeta as coordenadas e monta a base.

1. Município: o contorno que contém a UC. UC fora de todos os contornos fica de fora (e é contada).
2. Comunidade: a predominante entre os endereços de referência mais próximos, com peso pela
   distância (a mesma ideia da votação do algoritmo, agora sobre a base territorial).
3. Aviso: um por município, com as regras de sempre (comunidade inteira ou parte, fragmentos).
   O tamanho de cada comunidade (para decidir "inteira") é o número de endereços na base.
"""

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd
import shapely
from sklearn.neighbors import KDTree

from . import idiomas
from .desligamento import RegrasAviso, aviso_novo, duracao_s, resumir_por_total

K_VIZINHOS = 9           # endereços de referência que votam na comunidade de cada UC
SUAVIZACAO_M = 30.0      # peso 1 / (distância + isto): o endereço mais perto não decide sozinho
MARGEM_DIVISA_M = 500.0  # UC fora de todos os contornos, mas a menos disto de um: fica com o mais próximo
# (a malha do IBGE e as coordenadas não coincidem exatamente na divisa)


@dataclass(frozen=True)
class BaseMunicipio:
    """Base territorial de um município (coordenadas em metros, na mesma projeção das UCs)."""
    codigo: str
    nome: str
    uf: str
    contorno: shapely.Geometry
    xy: np.ndarray            # endereços de referência, (n, 2)
    comunidade: np.ndarray    # comunidade de cada endereço
    distrito: np.ndarray      # distrito de cada endereço

    def total(self) -> pd.Series:
        return pd.Series(self.comunidade).value_counts()


@dataclass
class ResultadoMunicipio:
    codigo: str
    nome: str
    uf: str
    ucs: pd.DataFrame                    # UCs do município, com COMUNIDADE_PREVISTA, DISTRITO e CONFIANCA
    comunidades: pd.DataFrame = field(default=None)
    aviso: str = ""
    segundos: int = 0


@dataclass
class Resultado:
    municipios: list[ResultadoMunicipio]
    fora: np.ndarray                     # posições (na planilha) das UCs fora de todos os municípios


def municipio_de(xy: np.ndarray, bases: list[BaseMunicipio], margem_m: float = MARGEM_DIVISA_M) -> np.ndarray:
    """Índice da base que contém cada ponto; fora de todas, a mais próxima até margem_m (-1 = fora)."""
    qual = np.full(len(xy), -1)
    for i, b in enumerate(bases):
        livre = qual == -1
        dentro = shapely.contains_xy(b.contorno, xy[livre, 0], xy[livre, 1])
        qual[np.where(livre)[0][dentro]] = i
    fora = np.where(qual == -1)[0]
    if len(fora) and bases:
        pts = shapely.points(xy[fora])
        dist = np.array([shapely.distance(b.contorno, pts) for b in bases])  # (bases, pontos)
        perto = dist.min(axis=0) <= margem_m
        qual[fora[perto]] = dist.argmin(axis=0)[perto]
    return qual


def comunidade_de(xy: np.ndarray, base: BaseMunicipio) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Comunidade, distrito e confiança (fração do peso do voto vencedor) de cada ponto."""
    k = min(K_VIZINHOS, len(base.xy))
    dist, idx = KDTree(base.xy).query(xy, k=k)
    pesos = 1.0 / (dist + SUAVIZACAO_M)
    nomes, conf, distritos = np.empty(len(xy), dtype=object), np.zeros(len(xy)), np.empty(len(xy), dtype=object)
    for i in range(len(xy)):
        placar = pd.Series(pesos[i]).groupby(base.comunidade[idx[i]]).sum()
        nomes[i] = placar.idxmax()
        conf[i] = placar.max() / placar.sum()
        # distrito: o do endereço mais próximo que votou na comunidade vencedora
        distritos[i] = base.distrito[idx[i][base.comunidade[idx[i]] == nomes[i]][0]]
    return nomes, conf.round(3), distritos


def localizar(xy: np.ndarray, bases: list[BaseMunicipio]) -> pd.DataFrame:
    """Município (índice da base, -1 = fora), comunidade, distrito e confiança de cada UC.
    O índice é a posição da UC na planilha (o número da UC não entra no núcleo)."""
    qual = municipio_de(xy, bases)
    loc = pd.DataFrame({"MUNICIPIO": qual, "COMUNIDADE_PREVISTA": None, "DISTRITO": None, "CONFIANCA": 0.0})
    for i, b in enumerate(bases):
        pos = np.where(qual == i)[0]
        if len(pos):
            nomes, conf, distritos = comunidade_de(xy[pos], b)
            loc.loc[pos, "COMUNIDADE_PREVISTA"], loc.loc[pos, "DISTRITO"], loc.loc[pos, "CONFIANCA"] = nomes, distritos, conf
    return loc


def avisar(loc: pd.DataFrame, bases: list[BaseMunicipio], regras: RegrasAviso,
           data: str = "12/11", horario: str = "8h às 14h", idioma: str = idiomas.PADRAO) -> Resultado:
    """Resumo e aviso de cada município a partir das UCs já localizadas (saída de localizar)."""
    resultado = []
    for i, b in enumerate(bases):
        ucs = loc[loc["MUNICIPIO"] == i].assign(UC=lambda d: d.index)
        if ucs.empty:
            continue
        r = replace(regras, municipio=b.nome)
        m = ResultadoMunicipio(b.codigo, b.nome, b.uf, ucs)
        m.comunidades = resumir_por_total(ucs, b.total(), r)
        m.aviso = aviso_novo(m.comunidades, data, horario, r, idioma)
        m.segundos = round(duracao_s(m.aviso))
        resultado.append(m)
    # o município com mais UCs afetadas primeiro (empate: ordem alfabética, estável)
    resultado.sort(key=lambda m: m.nome)
    resultado.sort(key=lambda m: len(m.ucs), reverse=True)
    return Resultado(resultado, loc.index[loc["MUNICIPIO"] == -1].to_numpy())


def afetados(xy: np.ndarray, bases: list[BaseMunicipio], regras: RegrasAviso,
             data: str = "12/11", horario: str = "8h às 14h", idioma: str = idiomas.PADRAO) -> Resultado:
    """xy: coordenadas das UCs da planilha (em metros), na ordem das linhas."""
    return avisar(localizar(xy, bases), bases, regras, data, horario, idioma)
