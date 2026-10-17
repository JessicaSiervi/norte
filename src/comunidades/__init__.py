"""Desafio 3: identificar as comunidades afetadas por um desligamento programado."""


def main() -> None:
    """Comando `comunidades`: executa o pipeline (ver pipeline.py).

    --distribuidora arquivo.toml  usa outra configuração (o município vem dela)
    --coordenada "lat,lon"        descobre o município pela malha do IBGE e usa a distribuidora dele
    """
    import os
    import sys

    argv = list(sys.argv)
    if "--coordenada" in argv:
        from . import localizar

        try:
            lat, lon = localizar.ler_coordenada(argv[argv.index("--coordenada") + 1])
            mun = localizar.municipio_da_coordenada(lat, lon)
        except (ValueError, IndexError) as e:
            sys.exit(f"Erro: {e}")
        arq, criado = localizar.distribuidora_do_municipio(mun)
        print(f"Coordenada em {mun['nome']}/{mun['uf']} (IBGE {mun['codigo']}). Distribuidora: {arq.name}", flush=True)
        if criado:
            print(f"ATENÇÃO: {arq.name} foi criado com os valores de demonstração do demo-leopoldina. "
                  "Revise os campos da distribuidora (nome, assinatura, telefone, prazos e perfis).", flush=True)
        argv += ["--distribuidora", str(arq)]
    if "--distribuidora" in argv:
        # o config.py lê o município daqui, então precisa vir antes de importar o pipeline
        os.environ["FAROL_DISTRIBUIDORA"] = argv[argv.index("--distribuidora") + 1]

    from .pipeline import executar

    executar(argv)
