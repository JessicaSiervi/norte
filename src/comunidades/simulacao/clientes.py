"""Cadastro FICTÍCIO de unidades consumidoras (UCs), como a distribuidora teria.

Cada endereço real do CNEFE vira uma UC com titular fictício e um campo
"BAIRRO_LOCALIDADE" digitado com o ruído típico de cadastro: vazio, abreviado,
com erro de digitação, com o nome da fazenda no lugar da comunidade ou
desatualizado. Parte das coordenadas também é ausente ou errada.

Saídas:
- sintetico/ucs.gpkg       -> o que o algoritmo pode ver
- sintetico/gabarito_uc.csv -> comunidade real de cada UC (só para avaliação)
"""

import re

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import config as C

# Multiplica as probabilidades de ruído no campo de localidade (vazio, imovel,
# vizinha, abreviado, digitacao). 1.0 = cadastro oficial; usado no teste de robustez.
FATOR_RUIDO = 1.0
TETO_RUIDO = 0.95  # a soma das probabilidades de ruído nunca passa disso

NOMES = ("JOSE MARIA ANTONIO JOAO FRANCISCO ANA LUIZ PAULO CARLOS MANOEL PEDRO FRANCISCA MARCOS "
         "RAIMUNDO SEBASTIAO ANTONIA MARCELO JORGE MARCIA GERALDO ADRIANA SANDRA LUIS FERNANDO "
         "FABIO ROBERTO MARCIO EDSON ANDRE SERGIO JOSEFA PATRICIA DANIEL RODRIGO RAFAEL JOAQUIM "
         "VERA RITA APARECIDA TEREZINHA BENEDITO LUZIA DIVINO GERALDA ODETE").split()
SOBRENOMES = ("SILVA SANTOS OLIVEIRA SOUZA RODRIGUES FERREIRA ALVES PEREIRA LIMA GOMES COSTA RIBEIRO "
              "MARTINS CARVALHO ALMEIDA LOPES SOARES FERNANDES VIEIRA BARBOSA ROCHA DIAS NASCIMENTO "
              "ANDRADE MOREIRA NUNES MARQUES MACHADO MENDES FREITAS CARDOSO RAMOS GONCALVES SANTANA "
              "TEIXEIRA REZENDE FARIA GUEDES MONTEIRO").split()
NOMES_IMOVEL = ("BOA VISTA|SANTA RITA|SAO JOSE|BOA ESPERANCA|SANTO ANTONIO|TRES IRMAOS|BELA VISTA|"
                "PARAISO|RECANTO|SAO JOAO|SANTA MARIA|AGUA LIMPA|PALMEIRAS|SOSSEGO|BOM JESUS|"
                "SANTA LUZIA|CACHOEIRA|BOA SORTE|VISTA ALEGRE|SAO PEDRO|PEDRA BRANCA|SANTA CLARA|"
                "MONTE ALEGRE|SAO SEBASTIAO|NOSSA SENHORA APARECIDA|DOIS IRMAOS|ESTRELA|CAFEZAL").split("|")

CLASSE = {"1": "Residencial", "2": "Residencial", "3": "Rural", "4": "Poder Público",
          "5": "Poder Público", "6": "Comercial", "8": "Comercial"}
# Atividade da UC (uma distribuidora real tem isso na subclasse ou na atividade da UC).
# Vem da espécie do endereço no CNEFE; usada só na janela de menor dano, nunca no algoritmo.
ATIVIDADE = {"1": "residencial", "2": "residencial", "3": "agropecuaria", "4": "ensino",
             "5": "saude", "6": "outros", "8": "religioso"}

ABREVIACOES = [
    (r"^CORREGO DO ", ["COR. DO ", "CORR DO ", "CGO DO ", ""]),
    (r"^CORREGO DAS ", ["COR. DAS ", "CORR DAS ", ""]),
    (r"^CORREGO ", ["COR. ", "CORR ", "CGO ", "CORREGO DO ", ""]),
    (r"^RIBEIRAO ", ["RIB. ", "RIB ", "RIBEIRAO DO "]),
    (r"\bSAO\b", ["S.", "S"]),
    (r"\bSANTA\b", ["STA", "STA."]),
    (r"\bSANTO\b", ["STO", "STO."]),
    (r"^JARDIM ", ["JD ", "JD. "]),
    (r"\bBOA\b", ["B."]),
]
PREFIXOS = ["COMUNIDADE ", "COM. ", "POVOADO ", "PROX. ", "ZONA RURAL - ", "Z.R. ", "REGIAO DO ", "LOCALIDADE "]
VAZIOS = ["", "", "ZONA RURAL", "Z RURAL", "AREA RURAL", "INTERIOR", "S/N"]


def _abreviar(nome: str, rng) -> str:
    regras = [(p, alts) for p, alts in ABREVIACOES if re.search(p, nome)]
    if regras:
        p, alts = regras[rng.integers(len(regras))]
        nome = re.sub(p, alts[rng.integers(len(alts))], nome, count=1).strip()
    if rng.random() < 0.5:
        nome = PREFIXOS[rng.integers(len(PREFIXOS))] + nome
    return nome


def _digitar_errado(nome: str, rng) -> str:
    if len(nome) < 4:
        return nome
    i = int(rng.integers(1, len(nome) - 1))
    op = rng.integers(4)
    if op == 0:  # troca letras vizinhas
        return nome[:i - 1] + nome[i] + nome[i - 1] + nome[i + 1:]
    if op == 1:  # come letra
        return nome[:i] + nome[i + 1:]
    if op == 2:  # duplica letra
        return nome[:i] + nome[i] + nome[i:]
    trocas = {"S": "Z", "Z": "S", "C": "S", "J": "G", "G": "J", "U": "O", "O": "U", "E": "I", "I": "E"}
    return nome[:i] + trocas.get(nome[i], nome[i]) + nome[i + 1:]


def _nome_imovel(row, rng) -> str:
    tipo, nome = row["NOM_TIPO_SEGLOGR"], str(row["NOM_SEGLOGR"] or "")
    if tipo in ("SITIO", "FAZENDA", "CHACARA") and nome and "SEM DENOMINACAO" not in nome:
        return f"{tipo} {re.sub(r'^(S|F|SITIO|FAZENDA) ', '', nome)}"
    tipo = rng.choice(["SITIO", "SITIO", "FAZENDA", "CHACARA"]) if row["COD_ESPECIE"] != "6" else "SITIO"
    return f"{tipo} {rng.choice(NOMES_IMOVEL)}"


def _escalar(limites: list[tuple[float, str]], fator: float) -> list[tuple[float, str]]:
    """Limites acumulados x fator; se a soma passar do teto, reduz todos na mesma proporção."""
    escala = fator * min(1.0, TETO_RUIDO / (limites[-1][0] * fator))
    return [(lim * escala, t) for lim, t in limites]


def construir(semente: int | None = None, fator_ruido: float | None = None):
    """semente e fator_ruido só mudam no teste de robustez; o padrão é o cadastro oficial."""
    semente = C.SEMENTE if semente is None else semente
    fator = FATOR_RUIDO if fator_ruido is None else fator_ruido
    rng = np.random.default_rng(semente)
    uc = gpd.read_file(C.SINTETICO / "uc_base.gpkg")
    n = len(uc)
    rural = (uc["ZONA"] == "Rural").to_numpy()
    real = uc["COMUNIDADE"].str.upper().to_numpy()

    uc["UC"] = (rng.permutation(n) + 3_000_000_000).astype(str)
    uc["TITULAR"] = [f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}" for _ in range(n)]
    uc["CLASSE"] = np.where(rural & uc["COD_ESPECIE"].isin(["1", "3"]), "Rural", uc["COD_ESPECIE"].map(CLASSE))
    uc["NOME_IMOVEL"] = [_nome_imovel(r, rng) if z else "" for (_, r), z in zip(uc.iterrows(), rural)]
    uc["ATIVIDADE"] = uc["COD_ESPECIE"].map(ATIVIDADE).fillna("outros")  # sem sorteio: não muda o resto

    partes = uc[["NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR"]].fillna("")
    uc["LOGRADOURO"] = partes.agg(" ".join, axis=1).str.replace(r"\s+", " ", regex=True).str.strip()
    uc["NUMERO"] = uc["NUM_ENDERECO"].replace({"0": "S/N"}).fillna("S/N")

    # Comunidades vizinhas (para simular cadastro desatualizado/errado)
    m = uc.to_crs(C.CRS_METRICO)
    cent = m.groupby(real).geometry.apply(lambda s: s.union_all().centroid)
    cxy = np.c_[cent.x, cent.y]
    vizinhas = {}
    for i, nome in enumerate(cent.index):
        d = np.hypot(*(cxy - cxy[i]).T)
        vizinhas[nome] = [cent.index[j] for j in np.argsort(d)[1:5]]

    # --- Ruído no campo de localidade ---
    lim_rural = _escalar([(0.22, "vazio"), (0.32, "imovel"), (0.37, "vizinha"), (0.55, "abreviado"), (0.63, "digitacao")], fator)
    lim_urbano = _escalar([(0.08, "vazio"), (0.08, "imovel"), (0.11, "vizinha"), (0.16, "abreviado"), (0.21, "digitacao")], fator)
    loc, tipo_ruido = [], []
    for i in range(n):
        nome, r = real[i], rng.random()
        limites = lim_rural if rural[i] else lim_urbano
        t = next((t for lim, t in limites if r < lim), "correto")
        if t == "vazio":
            v = VAZIOS[rng.integers(len(VAZIOS))]
        elif t == "imovel":
            v = re.sub(r"^FAZENDA ", rng.choice(["FAZ ", "FAZ. ", "FAZENDA "]),
                       re.sub(r"^SITIO ", rng.choice(["SIT ", "SITIO ", "ST. "]), uc["NOME_IMOVEL"].iat[i]))
        elif t == "vizinha":
            v = rng.choice(vizinhas[nome])
        elif t == "abreviado":
            v = _abreviar(nome, rng)
        elif t == "digitacao":
            v = _digitar_errado(nome, rng)
        else:
            v = nome
        loc.append(v)
        tipo_ruido.append(t)
    uc["BAIRRO_LOCALIDADE"] = loc

    # --- Ruído nas coordenadas ---
    x, y = m.geometry.x.to_numpy().copy(), m.geometry.y.to_numpy().copy()
    x += rng.normal(0, 8, n)
    y += rng.normal(0, 8, n)
    r = rng.random(n)
    p_aus = np.where(rural, 0.18, 0.06)
    ausente = r < p_aus
    padrao = (r >= p_aus) & (r < p_aus + 0.02)            # coordenada "padrão" = centro da cidade
    deslocada = (r >= p_aus + 0.02) & (r < p_aus + 0.04)  # erro grosseiro de 1 a 4 km
    sede = gpd.read_file(C.INTERIM / "localidades_oficiais.gpkg").to_crs(C.CRS_METRICO)
    ps = sede[sede["CT_LOCALIDADE"] == "Cidade"].geometry.iloc[0]
    x[padrao], y[padrao] = ps.x, ps.y
    ang = rng.uniform(0, 2 * np.pi, deslocada.sum())
    dist = rng.uniform(1000, 4000, deslocada.sum())
    x[deslocada] += np.cos(ang) * dist
    y[deslocada] += np.sin(ang) * dist
    pts = gpd.GeoSeries(gpd.points_from_xy(x, y), crs=C.CRS_METRICO).to_crs(C.CRS_GEO)
    lat = np.where(ausente, np.nan, pts.y.round(6))
    lon = np.where(ausente, np.nan, pts.x.round(6))
    uc["LATITUDE"], uc["LONGITUDE"] = lat, lon

    publicas = ["UC", "TITULAR", "CLASSE", "ATIVIDADE", "NOME_IMOVEL", "LOGRADOURO", "NUMERO", "BAIRRO_LOCALIDADE",
                "NM_DIST", "LATITUDE", "LONGITUDE", "COD_TRAFO", "ALIMENTADOR", "CHAVES_MONTANTE"]
    ucs = gpd.GeoDataFrame(uc[publicas].rename(columns={"NM_DIST": "DISTRITO"}),
                           geometry=gpd.points_from_xy(lon, lat), crs=C.CRS_GEO)
    ucs.to_file(C.SINTETICO / "ucs.gpkg")

    gab = pd.DataFrame({
        "UC": uc["UC"], "COMUNIDADE": uc["COMUNIDADE"], "ZONA": uc["ZONA"], "DISTRITO": uc["NM_DIST"],
        "RUIDO_LOCALIDADE": tipo_ruido,
        "RUIDO_COORD": np.select([ausente, padrao, deslocada], ["ausente", "padrao", "deslocada"], "ok"),
        "LAT_REAL": uc.geometry.y.round(6), "LON_REAL": uc.geometry.x.round(6),
    })
    gab.to_csv(C.SINTETICO / "gabarito_uc.csv", index=False, encoding="utf-8")
    return ucs, gab


if __name__ == "__main__":
    ucs, gab = construir()
    print(ucs.drop(columns="geometry").sample(12, random_state=3).to_string())
    print(pd.crosstab(gab.ZONA, gab.RUIDO_LOCALIDADE, normalize="index").round(2))
    print(pd.crosstab(gab.ZONA, gab.RUIDO_COORD, normalize="index").round(2))
