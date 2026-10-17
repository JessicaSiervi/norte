"""Área administrativa (PROTÓTIPO): saida/admin.html, com empresas e usuários fictícios.

Página autônoma, como o mapa: Model (admin_modelo.js), View e Controller (admin_template.html),
fontes embutidas e CSP com o hash de cada script. Tudo roda na memória do navegador: não há
servidor, login real nem conexão externa (connect-src 'none'). Recarregar volta à demonstração.

Os valores do arquivo de configuração (.toml) que o cadastro ainda não tem (expediente, limites
do aviso, perfis de sensibilidade) vêm da demonstração de Leopoldina (distribuidoras/demo-leopoldina.toml).

Uso: py -m uv run python -m comunidades.apresentacao.admin (o pipeline já roda no fim)
"""

import json
import tomllib
from pathlib import Path

from .. import distribuidora as dist_
from ..simulacao import empresas_demo
from .mapa import SAIDA_RAIZ, _fontes_embutidas, favicon, politica_seguranca, MARCA

TEMPLATE = Path(__file__).with_name("admin_template.html")
MODELO = Path(__file__).with_name("admin_modelo.js")
ARQ_ADMIN = SAIDA_RAIZ / "admin.html"
SECOES_PADRAO = ("regulatorio", "expediente", "aviso", "obra", "janela", "perfis")


def padroes_toml(arquivo: Path = dist_.PADRAO) -> dict:
    """As seções do .toml que vêm da demonstração (a empresa ajusta depois, com a distribuidora)."""
    with open(arquivo, "rb") as f:
        d = tomllib.load(f)
    return {s: d[s] for s in SECOES_PADRAO}


def construir() -> Path:
    dados = {"demo": empresas_demo.dados(), "padroesToml": padroes_toml(), "mapas": "index.html"}
    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("<!--__LOGO__-->", (MARCA / "norte-icone.svg").read_text(encoding="utf-8").strip())
            .replace("__FAVICON__", favicon())
            .replace("__MAPAS__", "index.html")
            .replace("/*__FONTES__*/", _fontes_embutidas())
            .replace("/*__MODELO__*/", MODELO.read_text(encoding="utf-8"))
            .replace("/*__DADOS__*/", json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))
    html = html.replace("/*__CSP__*/", politica_seguranca(html, fundo_mapa=False))
    ARQ_ADMIN.write_text(html, encoding="utf-8", newline="\n")
    return ARQ_ADMIN


if __name__ == "__main__":
    print(f"Área administrativa (protótipo): {construir()}")
