# -*- coding: utf-8 -*-
"""Lista (e, com --forcar, remove) diretórios de tenant órfãos em tenant_data/ (Fase 13, Task 18).

A auditoria de 16/set encontrou dezenas de diretórios de tenant de teste/benchmark acumulados em
`tenant_data/chroma/` e `tenant_data/tabular/` -- sobras de suítes que criam um tenant fictício
para testar isolamento multi-tenant e, por alguma falha pontual de `tearDown` (interrupção de
execução, exceção antes da limpeza), não o removem. Nenhum é dado de cliente: o único tenant real
é `senai_labfashion` (o único registrado em `tenant_config.TENANT_CONFIG`).

Complementa `rag_manager.limpar_indices_orfaos` (que limpa DENTRO do armazenamento de UM tenant
já conhecido -- collections não-canônicas, pastas de segmento sem linha em `segments`): este
script opera um nível acima, nos diretórios de tenant inteiros dentro de `tenant_data/`.

Uso:
    python scripts/limpar_tenants_orfaos.py                # lista, não apaga nada
    python scripts/limpar_tenants_orfaos.py --forcar        # remove de fato
    python scripts/limpar_tenants_orfaos.py --forcar --idade-minima-minutos 30
        # só remove o que não foi tocado nos últimos 30 min -- margem de segurança para não
        # apagar o diretório de um teste que esteja rodando neste exato momento noutro processo.
"""

import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tenant_config import TENANT_CONFIG

RAIZ_TENANT_DATA = os.path.join(os.path.dirname(__file__), "..", "tenant_data")
SUBDIRETORIOS_POR_TENANT = ("chroma", "tabular")


def _tamanho_em_mb(caminho: str) -> float:
    total = 0
    for raiz, _dirs, arquivos in os.walk(caminho):
        for nome in arquivos:
            try:
                total += os.path.getsize(os.path.join(raiz, nome))
            except OSError:
                pass
    return total / (1024 * 1024)


def _modificado_ha_menos_de(caminho: str, minutos: int) -> bool:
    if minutos <= 0:
        return False
    mais_recente = os.path.getmtime(caminho)
    for raiz, _dirs, arquivos in os.walk(caminho):
        for nome in arquivos:
            try:
                mais_recente = max(mais_recente, os.path.getmtime(os.path.join(raiz, nome)))
            except OSError:
                pass
    return (time.time() - mais_recente) < (minutos * 60)


def encontrar_orfaos(idade_minima_minutos: int = 0) -> dict:
    """Devolve {subdiretorio: [(nome_tenant, caminho, tamanho_mb), ...]} para tudo que não está
    em TENANT_CONFIG, ordenado por tamanho decrescente."""
    tenants_conhecidos = set(TENANT_CONFIG.keys())
    orfaos = {}
    for sub in SUBDIRETORIOS_POR_TENANT:
        caminho_sub = os.path.join(RAIZ_TENANT_DATA, sub)
        if not os.path.isdir(caminho_sub):
            orfaos[sub] = []
            continue
        achados = []
        for nome in sorted(os.listdir(caminho_sub)):
            caminho_tenant = os.path.join(caminho_sub, nome)
            if not os.path.isdir(caminho_tenant) or nome in tenants_conhecidos:
                continue
            if _modificado_ha_menos_de(caminho_tenant, idade_minima_minutos):
                continue
            achados.append((nome, caminho_tenant, _tamanho_em_mb(caminho_tenant)))
        orfaos[sub] = sorted(achados, key=lambda item: item[2], reverse=True)
    return orfaos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--forcar", action="store_true", help="Remove de fato -- sem isso, só lista.")
    parser.add_argument(
        "--idade-minima-minutos", type=int, default=0,
        help="Ignora diretórios modificados há menos tempo que isto (default: 0, sem filtro).",
    )
    args = parser.parse_args()

    orfaos = encontrar_orfaos(args.idade_minima_minutos)
    total_mb = 0.0
    total_dirs = 0

    for sub, achados in orfaos.items():
        if not achados:
            continue
        print(f"\ntenant_data/{sub}/ -- {len(achados)} diretório(s) órfão(s):")
        for nome, caminho, tamanho_mb in achados:
            print(f"  {nome:<45} {tamanho_mb:8.2f} MB")
            total_mb += tamanho_mb
            total_dirs += 1
            if args.forcar:
                shutil.rmtree(caminho, ignore_errors=True)

    if total_dirs == 0:
        print("Nenhum diretório de tenant órfão encontrado.")
    elif args.forcar:
        print(f"\nRemovidos: {total_dirs} diretório(s), {total_mb:.2f} MB liberados.")
    else:
        print(
            f"\nTotal: {total_dirs} diretório(s), {total_mb:.2f} MB -- nada foi removido "
            "(rode com --forcar para remover de fato)."
        )
