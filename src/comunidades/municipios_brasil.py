"""Carrega no banco os municípios do Brasil inteiro (malha do IBGE), para a área de atuação das empresas, e as regiões
do IBGE (microrregiões e regiões imediatas, a camada "Regiões do IBGE" do mapa).

Baixa uma vez por UF para data/raw/malhas (a mesma API e o mesmo cache de fontes/concessao.py) e grava na tabela
municipio_ibge (contorno simplificado e um ponto dentro). Pode rodar de novo: refaz só as UFs que faltam
(--refazer para todas). As regiões saem dos mesmos arquivos (banco/regioes_ibge.py), também só das UFs que faltam.

Uso (na raiz): uv run python -m comunidades.municipios_brasil [--refazer]
"""

import json
import sys

from .banco import municipios_ibge as banco
from .banco import regioes_ibge
from .banco.conexao import conectar
from .fontes import concessao


def main() -> None:
    refazer = "--refazer" in sys.argv
    banco.criar_esquema()
    nomes = concessao._baixar(f"{concessao.API}/v1/localidades/estados", concessao.PASTA / "nomes_ufs.json")
    siglas = sorted(u["sigla"] for u in json.loads(nomes.read_text(encoding="utf-8")))
    with conectar() as c:
        feitas = {r[0] for r in c.execute("SELECT DISTINCT uf FROM municipio_ibge").fetchall()}
    total = 0
    for uf in siglas:
        if uf in feitas and not refazer:
            continue
        n = banco.gravar_uf(uf, concessao._municipios_uf(uf))
        total += n
        print(f"  {uf}: {n} municípios", flush=True)
    with conectar() as c:
        n, ufs = c.execute("SELECT count(*), count(DISTINCT uf) FROM municipio_ibge").fetchone()
    print(f"municipio_ibge: {n} municípios em {ufs} UFs ({total} gravados agora)")
    regioes_ibge.criar_esquema()
    feitas = regioes_ibge.ufs_gravadas()
    for uf in siglas:
        if uf in feitas and not refazer:
            continue
        n = regioes_ibge.gravar_uf(uf, concessao.regioes_uf(uf))
        print(f"  {uf}: {n} regiões", flush=True)
    print("regiao_ibge:", ", ".join(f"{q} {regioes_ibge.NOME_TIPO[t].lower()}s" for t, q in regioes_ibge.totais().items()))


if __name__ == "__main__":
    main()
