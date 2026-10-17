"""Normalização de nomes de localidade digitados no cadastro e exibição com acentos."""

import re

from unidecode import unidecode

PREFIXOS = re.compile(
    r"^(COMUNIDADE( DE| DO| DA)?|COM\.?|POVOADO( DE| DO| DA)?|PROX\.?|PROXIMO A?O?|"
    r"ZONA RURAL ?-?|Z\.? ?R\.?|REGIAO D[OA]S?|LOCALIDADE( DE)?|BAIRRO)\s+"
)
EXPANSOES = [
    (r"^(COR\.?|CORR\.?|CGO\.?|CORREGO)\s+", "CORREGO "),
    (r"^(RIB\.?|RIBEIRAO)\s+", "RIBEIRAO "),
    (r"\bS\.?\s+(?=[A-Z])", "SAO "),
    (r"\bSTA\.?\s+", "SANTA "),
    (r"\bSTO\.?\s+", "SANTO "),
    (r"^JD\.?\s+", "JARDIM "),
    (r"\bB\.\s*", "BOA "),
]
VAZIO = re.compile(r"^(|ZONA RURAL|Z RURAL|AREA RURAL|INTERIOR|S/?N|RURAL|NAO INFORMADO)$")
PROPRIEDADE = re.compile(r"^(FAZ|FAZENDA|SIT|SITIO|ST|CHACARA|CHAC|HARAS|GRANJA)\b\.?")

# Reserva: grafia feita à mão (para Leopoldina). Só vale para palavras que as fontes do
# município (fontes/grafia.py) não trazem acentuadas.
ACENTOS = {
    "CORREGO": "Córrego", "RIBEIRAO": "Ribeirão", "SAO": "São", "ABAIBA": "Abaíba",
    "PROVIDENCIA": "Providência", "ESPERANCA": "Esperança", "BRAUNA": "Braúna", "TOME": "Tomé",
    "CAICARA": "Caiçara", "HORACIO": "Horácio", "FEIJAO": "Feijão", "LOURENCO": "Lourenço",
    "FABRICA": "Fábrica", "PARAISO": "Paraíso", "CRISTOVAO": "Cristóvão", "JOAO": "João",
    "JOSE": "José", "ANTONIO": "Antônio", "SEBASTIAO": "Sebastião", "CONCEICAO": "Conceição",
    "AGUA": "Água", "AGUAS": "Águas", "VARZEA": "Várzea", "IRMAOS": "Irmãos", "ESTACAO": "Estação",
    "PIRINEUS": "Pirineus", "MATOZINHO": "Matozinho", "ITAGUACI": "Itaguaçi", "LUZIANIA": "Luziânia",
}
MINUSCULAS = {"DO", "DA", "DOS", "DAS", "DE", "E"}


def normalizar(txt) -> str:
    if txt is None or (isinstance(txt, float) and txt != txt):
        return ""
    s = re.sub(r"\s+", " ", unidecode(str(txt)).upper()).strip(" -.,")
    s = PREFIXOS.sub("", s).strip()
    for padrao, troca in EXPANSOES:
        s = re.sub(padrao, troca, s)
    return re.sub(r"\s+", " ", s).strip()


def classificar(nome_normalizado: str) -> str:
    """'vazio', 'propriedade' ou 'nome'."""
    if VAZIO.match(nome_normalizado):
        return "vazio"
    if PROPRIEDADE.match(nome_normalizado):
        return "propriedade"
    return "nome"


def exibir(nome: str, acentos: dict | None = None) -> str:
    """'CORREGO SAO JOAO' -> 'Córrego São João'.

    acentos: grafia vinda das fontes do município ({"CEMITERIO": "Cemitério"}), montada em
    fontes/grafia.py; o dicionário manual ACENTOS é só a reserva."""
    acentos = acentos or {}
    partes = []
    for i, p in enumerate(normalizar(nome).split()):
        if i > 0 and p in MINUSCULAS:
            partes.append(p.lower())
        else:
            partes.append(acentos.get(p) or ACENTOS.get(p) or p.capitalize())
    return " ".join(partes)
