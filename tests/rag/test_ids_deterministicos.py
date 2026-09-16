# -*- coding: utf-8 -*-
"""Testes de ids determinísticos e reindexação incremental (Fase 13, Task 5).

## O defeito que estes testes existem para pegar

O id de cada chunk incluía `int(datetime.now().timestamp())` -- reindexar o mesmo documento sem
NENHUMA mudança produzia ids diferentes a cada chamada, então a única forma de evitar duplicação
era apagar a coleção inteira do arquivo (`remover_documento`) antes de reinserir tudo de novo, do
zero, mesmo quando 99% do conteúdo não mudou.

Com `_gerar_id_chunk` dependendo só de (arquivo, posição, conteúdo), reindexar sem mudanças produz
exatamente os mesmos ids -- e `collection.upsert()` (em vez de `add()`) os sobrescreve em vez de
duplicar. A reconciliação por diferença (ao final de `indexar_documento`) remove só os ids que
sobraram de uma versão anterior e não existem mais no conjunto atual.
"""

import os
import shutil
import unittest

import rag_manager as rm
from rag_config import RAG_CONFIG

TENANT_TESTE = "teste_fase13_ids_deterministicos"
NOME_ARQUIVO = "lista.txt"


class TestGeracaoDeId(unittest.TestCase):
    """`_gerar_id_chunk` é uma função pura -- sem custo de embedding para testar."""

    def test_mesma_entrada_produz_sempre_o_mesmo_id(self):
        id1 = rm._gerar_id_chunk("doc.pdf", 0, "texto qualquer")
        id2 = rm._gerar_id_chunk("doc.pdf", 0, "texto qualquer")
        self.assertEqual(id1, id2)

    def test_conteudo_diferente_produz_id_diferente(self):
        id1 = rm._gerar_id_chunk("doc.pdf", 0, "texto A")
        id2 = rm._gerar_id_chunk("doc.pdf", 0, "texto B")
        self.assertNotEqual(id1, id2)

    def test_indice_diferente_produz_id_diferente_mesmo_com_texto_igual(self):
        # Sem o índice no hash, duas linhas de uma tabela com texto idêntico (célula vazia
        # repetida, por exemplo) colidiriam no mesmo id e uma sobrescreveria a outra no upsert.
        id1 = rm._gerar_id_chunk("doc.pdf", 0, "mesmo texto")
        id2 = rm._gerar_id_chunk("doc.pdf", 1, "mesmo texto")
        self.assertNotEqual(id1, id2)

    def test_arquivo_diferente_produz_id_diferente(self):
        id1 = rm._gerar_id_chunk("a.pdf", 0, "texto")
        id2 = rm._gerar_id_chunk("b.pdf", 0, "texto")
        self.assertNotEqual(id1, id2)

    def test_nao_depende_do_relogio(self):
        import time
        id1 = rm._gerar_id_chunk("doc.pdf", 0, "texto qualquer")
        time.sleep(0.01)
        id2 = rm._gerar_id_chunk("doc.pdf", 0, "texto qualquer")
        self.assertEqual(id1, id2)


class TestReindexacaoIncremental(unittest.TestCase):
    """Testes de integração: usam a coleção real (embeddings reais, sem custo de API) para provar
    que o comportamento fim-a-fim funciona, não só a função isolada de geração de id."""

    def setUp(self):
        self._limpar()
        self._chunk_size_original = RAG_CONFIG["chunk_size"]
        # Chunk pequeno o bastante para o texto de teste virar vários chunks -- o cenário
        # interessante (reconciliação parcial) só aparece com mais de 1 chunk por documento.
        RAG_CONFIG["chunk_size"] = 80

    def tearDown(self):
        RAG_CONFIG["chunk_size"] = self._chunk_size_original
        self._limpar()

    def _limpar(self):
        caminho = os.path.join("tenant_data", "chroma", TENANT_TESTE)
        if os.path.exists(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        rm._CHROMA_CLIENTS.pop(TENANT_TESTE, None)

    def _itens(self, quantidade=7):
        return [
            f"Item numero {i} com descrição própria bem distinta uma da outra para virar chunk."
            for i in range(1, quantidade + 1)
        ]

    def _ids_atuais(self, colecao):
        return sorted(colecao.get(include=[])["ids"])

    def test_reindexar_conteudo_identico_nao_duplica_nem_muda_ids(self):
        texto = "\n\n".join(self._itens())
        rm.indexar_documento(TENANT_TESTE, NOME_ARQUIVO, texto)
        colecao = rm._obter_colecao_tenant(TENANT_TESTE)
        contagem_1 = colecao.count()
        ids_1 = self._ids_atuais(colecao)

        rm.indexar_documento(TENANT_TESTE, NOME_ARQUIVO, texto)
        contagem_2 = colecao.count()
        ids_2 = self._ids_atuais(colecao)

        self.assertEqual(contagem_1, contagem_2, "Reindexar sem mudanças duplicou chunks.")
        self.assertEqual(ids_1, ids_2, "Reindexar sem mudanças trocou os ids dos chunks.")

    def test_remover_um_item_reconcilia_sem_deixar_orfaos(self):
        itens = self._itens()
        rm.indexar_documento(TENANT_TESTE, NOME_ARQUIVO, "\n\n".join(itens))
        colecao = rm._obter_colecao_tenant(TENANT_TESTE)
        ids_antes = self._ids_atuais(colecao)
        self.assertEqual(len(ids_antes), 7)

        itens_editados = itens[:3] + itens[4:]  # remove o 4º item do meio
        n_depois = rm.indexar_documento(TENANT_TESTE, NOME_ARQUIVO, "\n\n".join(itens_editados))
        ids_depois = self._ids_atuais(colecao)

        self.assertEqual(n_depois, 6)
        self.assertEqual(colecao.count(), 6, "Sobrou chunk órfão do item removido.")

    def test_itens_inalterados_preservam_o_mesmo_id_apos_edicao(self):
        # A prova mais direta de que a reconciliação é por DIFERENÇA, não destrói-e-reconstrói:
        # os chunks que não mudaram mantêm o id de antes da edição.
        itens = self._itens()
        rm.indexar_documento(TENANT_TESTE, NOME_ARQUIVO, "\n\n".join(itens))
        colecao = rm._obter_colecao_tenant(TENANT_TESTE)
        ids_antes = set(self._ids_atuais(colecao))

        itens_editados = itens[:3] + itens[4:]
        rm.indexar_documento(TENANT_TESTE, NOME_ARQUIVO, "\n\n".join(itens_editados))
        ids_depois = set(self._ids_atuais(colecao))

        ids_dos_3_primeiros = {rm._gerar_id_chunk(NOME_ARQUIVO, i, itens[i]) for i in range(3)}
        self.assertTrue(ids_dos_3_primeiros.issubset(ids_antes))
        self.assertTrue(
            ids_dos_3_primeiros.issubset(ids_depois),
            "Chunks que não mudaram perderam o id -- a reconciliação recriou tudo em vez de "
            "preservar por diferença.",
        )

    def test_busca_continua_funcionando_apos_reindexacoes_sucessivas(self):
        itens = self._itens()
        for _ in range(3):  # reindexa o mesmo conteúdo várias vezes seguidas
            rm.indexar_documento(TENANT_TESTE, NOME_ARQUIVO, "\n\n".join(itens))

        resultados = rm.buscar_contexto_relevante(TENANT_TESTE, "Item numero 3", top_k=3)
        self.assertGreater(len(resultados), 0)
        self.assertTrue(any("Item numero 3" in r["texto"] for r in resultados))


if __name__ == "__main__":
    unittest.main()
