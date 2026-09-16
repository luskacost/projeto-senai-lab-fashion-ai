# -*- coding: utf-8 -*-
"""Migra a coleção RAG de um tenant do espaço de distância antigo (`l2`, coleção `docs_v2_*`)
para o novo (`cosine`, coleção `docs_v3_*`) -- Fase 13, Task 1.

## Por que uma migração é necessária

`rag_manager._obter_colecao_tenant` passou a criar a coleção com `hnsw:space="cosine"`
explícito (antes, caía no padrão silencioso `l2` do Chroma). O Chroma **não permite mudar o
espaço de distância de uma coleção já existente** -- por isso o nome da coleção também mudou de
`docs_v2_{tenant}` para `docs_v3_{tenant}`. Sem esta migração, o tenant simplesmente perderia
acesso a tudo que já indexou: a próxima busca criaria uma coleção v3 vazia, e o conteúdo antigo
ficaria orfão em `docs_v2_{tenant}`, existindo em disco mas inacessível pelo código.

## O que o script faz

Copia cada chunk da coleção v2 (texto, embedding e metadados, incluindo o `id` original) direto
para a coleção v3 -- **sem re-chunking**: se o script reprocessasse o texto bruto do zero, a
lógica atual de chunking/inferência de metadados (que já está sendo simplificada nas próximas
tasks da Fase 13) poderia produzir um resultado diferente do que foi indexado originalmente, e
sem necessidade -- a migração é só de espaço de distância, o conteúdo não mudou.

Não re-embeda o texto: o Chroma não expõe uma forma de reinterpretar embeddings já gravados sob
uma métrica diferente, mas a interpretação (cosine vs l2) é feita pelo Chroma na hora da busca via
HNSW, não pelos vetores em si -- os mesmos vetores normalizados (norma 1) são válidos nos dois
espaços; o que muda é só a fórmula que o Chroma aplica sobre eles ao calcular distância.

Ao final, remove a coleção v2 antiga (`limpar_indices_orfaos`, que já existe para higienizar
coleções não-canônicas) e verifica a contagem de chunks / uma busca de sanidade.

Uso:
    python scripts/migrar_colecao_rag_v2_para_v3.py <tenant_id> [--manter-v2]
"""

import argparse
import sys

sys.path.insert(0, ".")

import rag_manager as rm


def migrar(tenant_id: str, manter_v2: bool = False) -> None:
    client = rm.obter_cliente_chroma(tenant_id)
    nome_v2 = f"docs_v2_{tenant_id}"
    nome_v3 = f"docs_{rm.COLLECTION_VERSION}_{tenant_id}"

    if rm.COLLECTION_VERSION == "v2":
        raise SystemExit(
            f"COLLECTION_VERSION ainda é 'v2' -- nada para migrar (rag_manager.py não foi "
            f"atualizado, ou este script já rodou e a versão mudou de novo)."
        )

    nomes_existentes = {getattr(c, "name", c) for c in client.list_collections()}
    if nome_v2 not in nomes_existentes:
        print(f"Nenhuma coleção '{nome_v2}' encontrada para o tenant '{tenant_id}' -- nada a migrar.")
        return

    colecao_v2 = client.get_collection(name=nome_v2)
    total = colecao_v2.count()
    if total == 0:
        print(f"Coleção '{nome_v2}' existe mas está vazia -- nada a copiar.")
    else:
        dados = colecao_v2.get(include=["documents", "metadatas", "embeddings"])
        print(f"Lidos {len(dados['ids'])} chunks de '{nome_v2}'.")

        colecao_v3 = rm._obter_colecao_tenant(tenant_id)
        colecao_v3.add(
            ids=dados["ids"],
            documents=dados["documents"],
            embeddings=dados["embeddings"],
            metadatas=dados["metadatas"],
        )
        print(f"Copiados {colecao_v3.count()} chunks para '{nome_v3}' (espaço cosine).")

        if colecao_v3.count() != total:
            raise SystemExit(
                f"Contagem divergente após a cópia: v2 tinha {total}, v3 ficou com "
                f"{colecao_v3.count()}. Abortando a limpeza da coleção antiga -- investigar antes."
            )

    if not manter_v2:
        relatorio = rm.limpar_indices_orfaos(tenant_id)
        print(f"Coleções não-canônicas removidas: {relatorio['colecoes_removidas']}")
        print(f"Pastas de índice órfãs removidas: {relatorio['pastas_removidas']}")
    else:
        print(f"'--manter-v2' passado -- '{nome_v2}' preservada para conferência manual.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tenant_id")
    parser.add_argument(
        "--manter-v2", action="store_true",
        help="Não remove a coleção v2 antiga após a cópia (útil para conferir antes de limpar).",
    )
    args = parser.parse_args()
    migrar(args.tenant_id, manter_v2=args.manter_v2)
