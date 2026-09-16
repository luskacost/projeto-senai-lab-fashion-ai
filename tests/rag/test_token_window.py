# -*- coding: utf-8 -*-
"""Testes da garantia de janela de tokens do modelo de embeddings (Fase 13, Task 2).

## O defeito que este arquivo existe para pegar

`chunk_size` (rag_config.py) é um orçamento em CARACTERES (default 600), mas o modelo de
embeddings ativo (`paraphrase-multilingual-MiniLM-L12-v2`) só processa até `max_seq_length=128`
TOKENS. Medido contra o tokenizer real: um chunk de 600 caracteres em português técnico gera ~149
tokens -- 21 acima do limite. O sentence-transformers trunca o excesso silenciosamente no forward
(sem erro, sem log) -- a cauda de qualquer chunk cheio nunca é embeddada, embora apareça inteira
no texto enviado ao LLM.

`rag_manager._garantir_limite_de_tokens` mede via o tokenizer do próprio modelo (não estima por
caracteres) e bisseca só os chunks que de fato excedem. Estes testes usam o modelo de embeddings
real (não mockado) -- é a única forma de testar contagem de tokens de verdade -- mas não fazem
nenhuma chamada de API paga; o modelo já é carregado localmente por outras suítes de RAG.
"""

import unittest

import rag_manager as rm

# Texto propositalmente longo e repetitivo -- verificado manualmente que produz 149 tokens no
# tokenizer real do MiniLM (> 128, o limite do modelo).
TEXTO_QUE_EXCEDE_A_JANELA = (
    "A camisa social feminina em tecido Millie Denim Maskskin possui gola italiana, punho "
    "simples com dois botoes, pences frontais e traseiras, barra arredondada. "
) * 4
TEXTO_QUE_EXCEDE_A_JANELA = TEXTO_QUE_EXCEDE_A_JANELA[:600]

TEXTO_CURTO = "Gramatura: 128 g/m² | Largura: 145 cm."


class TestLimiteDeTokensDoModelo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.modelo = rm.obter_modelo_embeddings()
        cls.limite = rm._limite_de_tokens_do_modelo(cls.modelo)

    def test_o_texto_de_fixture_realmente_excede_o_limite(self):
        # Prova que o cenário de teste é real, não hipotético -- se esta asserção falhar, os
        # testes abaixo não estariam testando nada.
        n_tokens = rm._contar_tokens_em_lote(self.modelo, [TEXTO_QUE_EXCEDE_A_JANELA])[0]
        self.assertGreater(
            n_tokens, self.limite,
            f"Fixture de teste não excede mais a janela ({n_tokens} <= {self.limite}) -- "
            "ajustar o texto de exemplo.",
        )

    def test_chunk_curto_passa_intacto(self):
        chunks = [{"texto": TEXTO_CURTO, "pagina": 1}]
        resultado = rm._garantir_limite_de_tokens(chunks)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["texto"], TEXTO_CURTO)

    def test_chunk_longo_e_dividido_em_pedacos_dentro_do_limite(self):
        chunks = [{"texto": TEXTO_QUE_EXCEDE_A_JANELA, "pagina": 3, "aba": "Especificações"}]
        resultado = rm._garantir_limite_de_tokens(chunks)

        self.assertGreater(len(resultado), 1, "O chunk que excede a janela não foi dividido.")
        for pedaco in resultado:
            with self.subTest(pedaco=pedaco["texto"][:30]):
                n_tokens = rm._contar_tokens_em_lote(self.modelo, [pedaco["texto"]])[0]
                self.assertLessEqual(
                    n_tokens, self.limite,
                    f"Pedaço ainda excede a janela após a bisseção ({n_tokens} > {self.limite}).",
                )

    def test_metadados_originais_sao_preservados_em_cada_pedaco(self):
        chunks = [{"texto": TEXTO_QUE_EXCEDE_A_JANELA, "pagina": 3, "aba": "Especificações"}]
        resultado = rm._garantir_limite_de_tokens(chunks)
        for pedaco in resultado:
            self.assertEqual(pedaco["pagina"], 3)
            self.assertEqual(pedaco["aba"], "Especificações")

    def test_conteudo_nao_se_perde_na_bissecao(self):
        chunks = [{"texto": TEXTO_QUE_EXCEDE_A_JANELA, "pagina": 1}]
        resultado = rm._garantir_limite_de_tokens(chunks)
        texto_reconstruido = "".join(p["texto"].replace(" ", "") for p in resultado)
        texto_original_sem_espacos = TEXTO_QUE_EXCEDE_A_JANELA.replace(" ", "")
        self.assertEqual(texto_reconstruido, texto_original_sem_espacos)

    def test_lista_vazia_nao_carrega_o_modelo_desnecessariamente(self):
        # Documento vazio (0 chunks) não deveria pagar o custo de carregar o modelo de
        # embeddings só para descobrir que não há nada para verificar.
        self.assertEqual(rm._garantir_limite_de_tokens([]), [])

    def test_multiplos_chunks_so_bisseca_os_que_excedem(self):
        chunks = [
            {"texto": TEXTO_CURTO, "pagina": 1},
            {"texto": TEXTO_QUE_EXCEDE_A_JANELA, "pagina": 2},
            {"texto": TEXTO_CURTO, "pagina": 3},
        ]
        resultado = rm._garantir_limite_de_tokens(chunks)
        # Os 2 chunks curtos passam intactos (1 pedaço cada); o longo vira >= 2 pedaços.
        self.assertGreaterEqual(len(resultado), 4)
        textos_curtos_presentes = sum(1 for c in resultado if c["texto"] == TEXTO_CURTO)
        self.assertEqual(textos_curtos_presentes, 2)


class TestIndexacaoRespeitaAJanela(unittest.TestCase):
    """Teste de integração: um documento com um chunk propositalmente maior que a janela do
    modelo, indexado de ponta a ponta, não deve deixar nenhum chunk fora do limite no Chroma."""

    TENANT_TESTE = "teste_fase13_token_window"

    def setUp(self):
        self._limpar()

    def tearDown(self):
        self._limpar()

    def _limpar(self):
        import shutil
        import os
        caminho = os.path.join("tenant_data", "chroma", self.TENANT_TESTE)
        if os.path.exists(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        rm._CHROMA_CLIENTS.pop(self.TENANT_TESTE, None)

    def test_nenhum_chunk_indexado_excede_a_janela_do_modelo(self):
        # Página curta o bastante para não passar pelo split por tamanho_chunk (600 chars) do
        # dividir_pagina_em_chunks, mas cujo texto, sozinho, já excede a janela de tokens --
        # exatamente o cenário que só a checagem por tokenização pega.
        rm.indexar_documento(self.TENANT_TESTE, "doc_longo.txt", TEXTO_QUE_EXCEDE_A_JANELA)

        colecao = rm._obter_colecao_tenant(self.TENANT_TESTE)
        dados = colecao.get(include=["documents"])
        modelo = rm.obter_modelo_embeddings()
        limite = rm._limite_de_tokens_do_modelo(modelo)

        contagens = rm._contar_tokens_em_lote(modelo, dados["documents"])
        for texto, n_tokens in zip(dados["documents"], contagens):
            with self.subTest(texto=texto[:30]):
                self.assertLessEqual(n_tokens, limite)


if __name__ == "__main__":
    unittest.main()
