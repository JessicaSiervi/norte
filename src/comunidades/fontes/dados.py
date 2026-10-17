"""Download dos dados brutos do IBGE (feito uma vez; depois reaproveita o que já está em data/raw).

Os endereços vêm do município da distribuidora ativa (código IBGE e UF): o CNEFE é por
município; setores e localidades são por UF e ficam compartilhados entre municípios.
"""

import re
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .. import config as C

CNEFE_PASTA_UF = ("https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
                  "Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/{cod_uf}_{uf}/")
LOCALIDADES = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/"
               "Localidades_do_Brasil/2022/Localidades_UFs_gpkg.zip")
SETORES = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
           "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/setores/shp/UF/{uf}_setores_CD2022.zip")


def _baixar(url: str, destino: Path):
    print(f"  baixando {destino.name} (pode levar alguns minutos)...", flush=True)
    tmp = destino.with_suffix(".parcial")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.replace(destino)


def _zip_cnefe() -> tuple[str, str]:
    """(nome, url) do zip do CNEFE do município. Tenta o nome padrão; se não existir,
    procura na listagem da pasta da UF o arquivo que começa pelo código IBGE."""
    pasta = CNEFE_PASTA_UF.format(cod_uf=C.COD_MUNICIPIO[:2], uf=C.UF)
    nome = f"{C.COD_MUNICIPIO}_{C.NOME_ARQUIVO_IBGE}.zip"
    if (C.RAW / nome).exists():
        return nome, pasta + nome
    try:
        with urllib.request.urlopen(urllib.request.Request(pasta + nome, method="HEAD"), timeout=60):
            return nome, pasta + nome
    except Exception:
        with urllib.request.urlopen(pasta, timeout=60) as r:
            listagem = r.read().decode("latin1")
        achados = re.findall(rf'href="({C.COD_MUNICIPIO}_[^"]+\.zip)"', listagem)
        if not achados:
            raise RuntimeError(f"CNEFE do município {C.COD_MUNICIPIO} não encontrado em {pasta}")
        return achados[0], pasta + achados[0]


def garantir():
    C.RAW.mkdir(parents=True, exist_ok=True)
    if not C.ARQ_CNEFE.exists():
        nome, url = _zip_cnefe()
        if not (C.RAW / nome).exists():
            _baixar(url, C.RAW / nome)
        zipfile.ZipFile(C.RAW / nome).extractall(C.RAW / "cnefe")
        csvs = sorted((C.RAW / "cnefe").glob(f"{C.COD_MUNICIPIO}_*.csv"))
        if not csvs:
            raise RuntimeError(f"o zip {nome} não trouxe o CSV do CNEFE do município {C.COD_MUNICIPIO}")
        C.ARQ_CNEFE = csvs[0]
    if not C.ARQ_LOCALIDADES.exists():
        zip_loc = C.RAW / "Localidades_UFs_gpkg.zip"
        if not zip_loc.exists():
            _baixar(LOCALIDADES, zip_loc)
        with zipfile.ZipFile(zip_loc) as z:
            z.extractall(C.RAW / "localidades", members=[m for m in z.namelist() if m.startswith(f"{C.UF}/")])
    if not C.ARQ_SETORES.exists():
        zip_set = C.RAW / f"{C.UF}_setores_CD2022.zip"
        if not zip_set.exists():
            _baixar(SETORES.format(uf=C.UF), zip_set)
        zipfile.ZipFile(zip_set).extractall(C.ARQ_SETORES.parent)


if __name__ == "__main__":
    garantir()
