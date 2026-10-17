"""Teste das regiões do IBGE (microrregiões e regiões imediatas, a camada "Regiões do IBGE" do mapa): banco e API.

Roda num esquema próprio para o acesso (FAROL_ESQUEMA=teste_regioes), apagado no fim; as regiões e os municípios são lidos
da base pública (carga: uv run python -m comunidades.municipios_brasil). Confere:
- o banco: os dois tipos carregados no Brasil inteiro; cada município está em uma região de cada tipo; o contorno da região
  contém o ponto de cada município dela e tem a área da soma deles (a junção não deixa frestas nem sobras);
- Leopoldina: microrregião Cataguases (31066) e região imediata Cataguases (310032), como na API do IBGE;
- a API: os três perfis da empresa veem; o Admin do Norte (403) e quem não entrou (401) não; tipo inválido é 422; só as
  regiões que tocam a área da empresa, cada município da área em uma região de cada tipo; dado público, sem dado pessoal.

Uso (na raiz): uv run python -W ignore testes/api/teste_regioes.py
"""

import os
import re
import sys

os.environ["FAROL_ESQUEMA"] = "teste_regioes"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(consulta, args=()):
    with conectar() as c:
        cur = c.execute(consulta, args)
        return cur.fetchall() if cur.description else []


LEOPOLDINA, UBA = "3138401", "3169901"

# ---------- 1. O banco ----------
por_tipo = dict(sql("SELECT tipo, count(*) FROM regiao_ibge GROUP BY tipo"))
conferir("microrregiões e regiões imediatas do Brasil inteiro (cerca de 510 a 560 de cada)",
         set(por_tipo) == {"micro", "imediata"} and all(480 <= n <= 600 for n in por_tipo.values()), str(por_tipo))
n_mun = sql("SELECT count(*) FROM municipio_ibge")[0][0]
for tipo in ("micro", "imediata"):
    vezes = sql("SELECT count(*) FILTER (WHERE n = 1), count(*) FILTER (WHERE n > 1) FROM (SELECT m.codigo_ibge, count(r.codigo) AS n"
                " FROM municipio_ibge m LEFT JOIN regiao_ibge r ON r.tipo = %s AND m.codigo_ibge = ANY(r.municipios) GROUP BY 1) q", (tipo,))[0]
    conferir(f"{tipo}: cada município em uma região só (nenhum em duas; no máximo 5 sem região na lista do IBGE)",
             vezes[1] == 0 and n_mun - vezes[0] <= 5, f"{vezes[0]} de {n_mun} em uma, {vezes[1]} em mais de uma")
fora = sql("SELECT count(*) FROM regiao_ibge r JOIN municipio_ibge m ON m.codigo_ibge = ANY(r.municipios)"
           " WHERE NOT ST_Intersects(r.contorno, m.ponto)")[0][0]
conferir("o contorno de cada região contém o ponto de todos os municípios dela", fora == 0, str(fora))
diferentes = sql("SELECT r.tipo, r.codigo, ST_Area(r.contorno::geography) / sum(ST_Area(m.contorno::geography)) FROM regiao_ibge r"
                 " JOIN municipio_ibge m ON m.codigo_ibge = ANY(r.municipios) GROUP BY r.tipo, r.codigo, r.contorno"
                 " HAVING abs(ST_Area(r.contorno::geography) / sum(ST_Area(m.contorno::geography)) - 1) > 0.02")
conferir("a área de cada região é a soma da área dos municípios dela (diferença de até 2%)", not diferentes, str(diferentes[:5]))
leo = dict(sql("SELECT tipo, codigo || ' ' || nome FROM regiao_ibge WHERE %s = ANY(municipios)", (LEOPOLDINA,)))
conferir("Leopoldina: microrregião Cataguases (31066) e região imediata Cataguases (310032)",
         leo == {"micro": "31066 Cataguases", "imediata": "310032 Cataguases"}, str(leo))
colunas = {r[0] for r in sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'regiao_ibge'")}
conferir("só colunas públicas: tipo, código, nome, UF, municípios, contorno e ponto",
         colunas == {"tipo", "codigo", "nome", "uf", "municipios", "contorno", "ponto"}, str(sorted(colunas)))

# ---------- 2. A API ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_regioes CASCADE")
senhas = {email: s for _, email, s in semear()}
NOVA = "Lanterna-do-Norte-2026"


def entrar(email):
    api_acesso._tentativas_ip.clear()
    cl = TestClient(app, base_url="http://farol.teste")
    cl.post("/api/entrar", json={"email": email, "senha": senhas[email]})
    cl.post("/api/senha", json={"atual": senhas[email], "nova": NOVA})
    return cl


op, adm = entrar("operador@emg.example"), entrar("admin@emg.example")
con, nor = entrar("consulta@emg.example"), entrar("admin@farol.example")
dono = sql("SELECT empresa_id FROM usuario WHERE email = 'operador@emg.example'")[0][0]
area = sorted(r[0] for r in sql("SELECT codigo_ibge FROM empresa_municipio WHERE empresa_id = %s", (dono,)))
for tipo in ("micro", "imediata"):
    r = op.get(f"/api/regioes?tipo={tipo}")
    j = r.json()
    fs = j.get("regioes", {}).get("features", [])
    conferir(f"Operador, {tipo}: regiões com a fonte e o tipo", r.status_code == 200 and j["fonte"] == "IBGE" and j["tipo"] == tipo and fs,
             f"{r.status_code} {len(fs)}")
    cobertos = sql("SELECT count(DISTINCT m) FROM regiao_ibge, unnest(municipios) m WHERE tipo = %s AND codigo = ANY(%s) AND m = ANY(%s)",
                   (tipo, [f["properties"]["codigo"] for f in fs], area))[0][0]
    conferir(f"{tipo}: os {len(area)} municípios da área da empresa estão nas regiões devolvidas, e a soma de na_area fecha",
             cobertos == len(area) and sum(f["properties"]["na_area"] for f in fs) == len(area), f"{cobertos} {sum(f['properties']['na_area'] for f in fs)}")
    conferir(f"{tipo}: cada região tem contorno, nome, UF e um ponto na região da concessão",
             all(f["geometry"]["type"] == "MultiPolygon" and f["properties"]["nome"] and re.fullmatch(r"[A-Z]{2}", f["properties"]["uf"])
                 and 0 < f["properties"]["na_area"] <= f["properties"]["municipios"] and -23.5 < f["properties"]["ponto"][0] < -19
                 and -45.5 < f["properties"]["ponto"][1] < -40.5 for f in fs))
padrao = op.get("/api/regioes").json()
conferir("sem tipo, vem a microrregião", padrao.get("tipo") == "micro")
conferir("tipo inválido: 422", op.get("/api/regioes?tipo=meso").status_code == 422)
conferir("Admin da empresa e Consulta também veem (dado público)",
         adm.get("/api/regioes").status_code == 200 and con.get("/api/regioes?tipo=imediata").status_code == 200)
conferir("Admin do Norte não vê o mapa operacional (403)", nor.get("/api/regioes").status_code == 403)
conferir("sem login: 401", TestClient(app, base_url="http://farol.teste").get("/api/regioes").status_code == 401)
texto = str([f["properties"] for f in padrao["regioes"]["features"]])
conferir("as propriedades não têm nada além de código, nome, UF, contagens e o ponto (nenhum e-mail ou número longo)",
         not re.search(r"(?<![.\d-])\d{7,}", texto) and "@" not in texto)

# ---------- 3. O isolamento pela área de atuação ----------
sql("DELETE FROM empresa_municipio WHERE empresa_id = %s AND codigo_ibge <> %s", (dono, UBA))
for tipo in ("micro", "imediata"):
    fs = op.get(f"/api/regioes?tipo={tipo}").json()["regioes"]["features"]
    esperado = sql("SELECT codigo FROM regiao_ibge WHERE tipo = %s AND %s = ANY(municipios)", (tipo, UBA))
    conferir(f"{tipo}: com a área só em Ubá, vem só a região de Ubá, com 1 município na área",
             [f["properties"]["codigo"] for f in fs] == [r[0] for r in esperado] and fs[0]["properties"]["na_area"] == 1, str([f["properties"] for f in fs]))

with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_regioes CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
