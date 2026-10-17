"""Os .toml gerados pela área administrativa (protótipo) carregam no distribuidora.py?

Recebe uma pasta com arquivos .toml (o teste testes/admin/teste_modelo.mjs grava os das empresas
de demonstração em saida/admin_toml_teste/) e carrega cada um com distribuidora.carregar, que
confere todos os campos obrigatórios, tipos, idioma e perfis. Também confere que nenhum arquivo
leva e-mail (os .toml nunca levam usuários).

Uso: py -m uv run python -m comunidades.validacao.configuracao_admin saida/admin_toml_teste
"""

import re
import sys
from pathlib import Path

from .. import distribuidora as dist_


def conferir(pasta: Path) -> list[str]:
    erros = []
    arquivos = sorted(pasta.glob("*.toml"))
    if not arquivos:
        return [f"nenhum .toml em {pasta}"]
    for a in arquivos:
        try:
            d = dist_.carregar(a)
            print(f"OK  {a.name}: {d.nome} · {d.municipio}/{d.uf} · {d.idioma_padrao} · {d.prazo_legal_horas} h · {len(d.perfis)} perfis")
        except Exception as e:  # noqa: BLE001 - o relatório mostra qualquer erro de leitura
            erros.append(f"{a.name}: {type(e).__name__}: {e}")
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", a.read_text(encoding="utf-8")):
            erros.append(f"{a.name}: contém um e-mail")
    return erros


if __name__ == "__main__":
    erros = conferir(Path(sys.argv[1] if len(sys.argv) > 1 else "saida/admin_toml_teste"))
    for e in erros:
        print(f"ERRO {e}")
    sys.exit(1 if erros else 0)
