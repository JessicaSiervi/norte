"""Rede elétrica FICTÍCIA dos municípios da concessão no banco (só para a demonstração no mapa).

Para cada município já na base territorial (base_concessao.py), num processo separado com o município
configurado (data/concessao/<código>.toml): monta o grafo viário com as vias do OSM do Sudeste
(fontes/osm_regiao.py, sem Overpass), traça a rede como em Leopoldina (simulacao/rede.py: trafos pelos
endereços do CNEFE, média tensão pelas vias, chaves no início dos ramais) e grava no banco (banco/rede.py).
Leopoldina usa a rede que já existe em data/sintetico (a mesma das planilhas de teste e das referências).
Nada de cliente: só a rede. Um município que falha não interrompe os outros.

Uso:
  uv run python -m comunidades.rede_concessao             # os municípios que ainda não têm rede
  uv run python -m comunidades.rede_concessao --refazer   # todos de novo
  uv run python -m comunidades.rede_concessao --so 3115300,3169901
"""

import json
import os
import subprocess
import sys
import time

from . import config as C

MARCA = "RESULTADO "
MARGEM_VIAS_M = 1000          # vias até esta distância além do contorno (como em fontes/osm.py)


def _um_municipio() -> None:
    """Roda dentro do processo do município (config já aponta para ele)."""
    import geopandas as gpd

    from .banco import rede as banco_rede
    from .simulacao import rede

    if C.COD_MUNICIPIO == C.MUNICIPIO_PASTAS_ORIGINAIS:   # Leopoldina: a rede de sempre
        camadas = [gpd.read_file(C.SINTETICO / f"{n}.gpkg") for n in ("subestacao", "rede_mt", "chaves", "transformadores")]
    else:
        from .fontes import osm_regiao
        mun = gpd.read_file(C.INTERIM / "municipio.gpkg").to_crs(C.CRS_METRICO)
        area = mun.buffer(MARGEM_VIAS_M).to_crs(C.CRS_GEO).union_all()
        se, mt, ch, tr, _ = rede.construir(osm_regiao.grafo(area), so_rede=True)
        camadas = [g.to_crs(C.CRS_GEO) for g in (se, mt, ch, tr)]
    se, mt, ch, tr = camadas
    banco_rede.gravar(C.COD_MUNICIPIO, se, mt, ch, tr)
    print(MARCA + json.dumps({"trafos": len(tr), "chaves": len(ch), "km": round(float(mt.to_crs(C.CRS_METRICO).length.sum()) / 1000),
                              "alimentadores": int(mt["ALIMENTADOR"].nunique())}), flush=True)


def executar(argv: list[str]) -> int:
    from .banco import base_territorial as banco
    from .banco import rede as banco_rede
    from .fontes import osm_regiao

    banco_rede.criar_esquema()
    osm_regiao.extrair()   # uma vez, antes dos processos
    ms = banco.municipios_gravados()
    so = set(argv[argv.index("--so") + 1].split(",")) if "--so" in argv else None
    feitos = set() if "--refazer" in argv else banco_rede.municipios_com_rede()
    fila = sorted((cod for cod in ms if (so is None or cod in so) and cod not in feitos), key=lambda c: ms[c]["nome"])
    print(f"Base territorial: {len(ms)} municípios; com rede: {len(feitos & set(ms))}; a processar: {len(fila)}", flush=True)
    falhas = []
    for i, cod in enumerate(fila, 1):
        t0 = time.time()
        rotulo = f"[{i}/{len(fila)}] {ms[cod]['nome']}/{ms[cod]['uf']} ({cod})"
        toml = C.DADOS / "concessao" / f"{cod}.toml"
        if not toml.exists():
            falhas.append((rotulo, f"falta {toml.name} (rode o base_concessao)"))
            print(f"{rotulo}: FALHOU: falta {toml}", flush=True)
            continue
        env = {**os.environ, "FAROL_DISTRIBUIDORA": str(toml), "PYTHONIOENCODING": "utf-8"}
        p = subprocess.run([sys.executable, "-m", "comunidades.rede_concessao", "--um"], env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        linha = next((l for l in p.stdout.splitlines() if l.startswith(MARCA)), None)
        if p.returncode or not linha:
            erro = (p.stderr.strip().splitlines() or ["sem mensagem"])[-1]
            falhas.append((rotulo, erro))
            print(f"{rotulo}: FALHOU em {time.time() - t0:.0f} s: {erro}", flush=True)
            continue
        r = json.loads(linha[len(MARCA):])
        print(f"{rotulo}: {r['alimentadores']} alimentadores, {r['km']} km de média tensão, {r['chaves']} chaves, "
              f"{r['trafos']} trafos | {time.time() - t0:.0f} s", flush=True)
    print(f"\nCom rede no banco: {len(banco_rede.municipios_com_rede() & set(ms))} de {len(ms)} municípios. "
          f"Falhas nesta rodada: {len(falhas)}")
    for rotulo, erro in falhas:
        print(f"  {rotulo}: {erro}")
    return 1 if falhas else 0


if __name__ == "__main__":
    if "--um" in sys.argv:
        _um_municipio()
    else:
        sys.exit(executar(sys.argv[1:]))
