# -*- coding: utf-8 -*-
"""Mede o baseline oficial do RAG contra o golden set (Fase 13, Task 9).

Roda os 36 casos de `rag_golden_set.py` contra o pipeline de retrieval de verdade (custo zero de
API -- ver `rag_eval.py`), e grava dois artefatos versionados na raiz do repositório:

- `rag_baseline_fase13.json`: o resumo agregado (`rag_eval.resumir_avaliacao`), para qualquer
  script ou teste futuro comparar contra ele via `rag_eval.comparar_resumos()`.
- Um relatório legível impresso no terminal (`rag_eval.formatar_resumo`) -- a mesma saída que vai
  para `RAG_BASELINE_FASE13.md`.

Este é o número contra o qual toda mudança do Bloco F3 (Tasks 10-14) é medida: uma mudança só
entra se o número deste arquivo melhorar. Rodar de novo e sobrescrever `rag_baseline_fase13.json`
é uma decisão consciente (nova baseline), não um efeito colateral -- por isso o script pede
confirmação antes de sobrescrever um arquivo já existente.

Uso:
    python scripts/medir_baseline_rag.py --rotulo "descricao do estado" [--k 5] [--forcar]
"""

import argparse
import json
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rag_eval
import rag_golden_set as gs
import rag_manager as rm
from rag_config import RAG_CONFIG

# O relatório de debug verbose do RAG (RAG_DEBUG=True por padrão) despeja o pool inteiro de
# candidatos por consulta -- ilegível para 36 casos numa tela. Este script quer só o resumo final.
RAG_CONFIG["debug"] = False
logging.disable(logging.CRITICAL)

CAMINHO_BASELINE = os.path.join(os.path.dirname(__file__), "..", "rag_baseline_fase13.json")
TENANT_MEDICAO = "rag_baseline_medicao"


def medir(k: int, rotulo: str) -> dict:
    caminho_chroma = os.path.join("tenant_data", "chroma", TENANT_MEDICAO)
    shutil.rmtree(caminho_chroma, ignore_errors=True)
    rm._CHROMA_CLIENTS.pop(TENANT_MEDICAO, None)

    try:
        gs.indexar_corpus(TENANT_MEDICAO)
        casos = gs.casos(TENANT_MEDICAO)
        resultados = rag_eval.executar_conjunto(casos, k=k)
        chunks = rag_eval.carregar_chunks_do_tenant(TENANT_MEDICAO)
        resumo = rag_eval.resumir_avaliacao(
            casos, resultados, chunks, k=k, rotulo=rotulo
        )
    finally:
        gs.remover_corpus(TENANT_MEDICAO)
        shutil.rmtree(caminho_chroma, ignore_errors=True)

    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=5, help="Chunks avaliados por caso (default: 5).")
    parser.add_argument(
        "--forcar", action="store_true",
        help="Sobrescreve rag_baseline_fase13.json existente sem perguntar.",
    )
    parser.add_argument(
        "--rotulo", required=True,
        help="Descrição do estado medido (ex: 'pos correcao do motor tabular') -- fica no JSON.",
    )
    args = parser.parse_args()

    if os.path.exists(CAMINHO_BASELINE) and not args.forcar:
        raise SystemExit(
            f"'{CAMINHO_BASELINE}' já existe. Rodar de novo e sobrescrever é registrar uma NOVA "
            "baseline -- passe --forcar se é isso mesmo que você quer."
        )

    resumo = medir(k=args.k, rotulo=args.rotulo)
    print(rag_eval.formatar_resumo(resumo))

    with open(CAMINHO_BASELINE, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    print(f"\nBaseline salvo em: {CAMINHO_BASELINE}")
