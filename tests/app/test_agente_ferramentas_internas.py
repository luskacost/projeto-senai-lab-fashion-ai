# -*- coding: utf-8 -*-
"""Testes das ferramentas internas novas (Fase 10, Bloco A, Task 2):
buscar_documentos_internos, listar_documentos_disponiveis, consultar_resumo_planilha,
consultar_unidades_senai."""

import unittest
from unittest.mock import patch

from agente_ferramentas import ContextoExecucao, executar_ferramenta, listar_nomes


class TestFerramentasRegistradas(unittest.TestCase):

    def test_quatro_ferramentas_internas_registradas(self):
        nomes = listar_nomes()
        for esperado in [
            "buscar_documentos_internos",
            "listar_documentos_disponiveis",
            "consultar_resumo_planilha",
            "consultar_unidades_senai",
        ]:
            self.assertIn(esperado, nomes)


class TestBuscarDocumentosInternos(unittest.TestCase):

    def setUp(self):
        self.ctx = ContextoExecucao(tenant_id="senai_labfashion", conversation_id="conv1")

    @patch("rag_manager.montar_prompt_final")
    @patch("rag_manager.buscar_contexto_relevante")
    def test_com_resultados_devolve_prompt_formatado_e_fontes(self, mock_buscar, mock_montar):
        # Fase 13, Task 17: "fontes" é uma LISTA na mesma ordem/tamanho de "trechos" -- dois
        # chunks da MESMA fonte (duas páginas do mesmo manual) precisam gerar duas entradas
        # paralelas, não colapsar num conjunto deduplicado que desalinha o pareamento por índice
        # que agente_openai._normalizar_fontes_de_tool faz entre "fontes" e "trechos".
        mock_buscar.return_value = [
            {"fonte": "manual.pdf", "texto": "trecho da pagina 3", "pagina": 3},
            {"fonte": "manual.pdf", "texto": "trecho da pagina 7", "pagina": 7},
        ]
        mock_montar.return_value = (
            "--- TRECHO 1 ---\ntrecho da pagina 3\n--- TRECHO 2 ---\ntrecho da pagina 7",
            ["manual.pdf (Página 3)", "manual.pdf (Página 7)"],
        )

        resultado = executar_ferramenta("buscar_documentos_internos", {"query": "gramatura do tecido"}, self.ctx)

        self.assertFalse(resultado.erro)
        self.assertIn("trecho da pagina 3", resultado.conteudo)
        self.assertEqual(
            resultado.dados_extras["fontes"], ["manual.pdf (Página 3)", "manual.pdf (Página 7)"]
        )
        self.assertEqual(len(resultado.dados_extras["fontes"]), len(resultado.dados_extras["trechos"]))
        mock_buscar.assert_called_once_with(
            "senai_labfashion", "gramatura do tecido", top_k=10, conversation_id="conv1"
        )

    @patch("rag_manager.buscar_contexto_relevante", return_value=[])
    def test_sem_resultados_nao_e_erro(self, mock_buscar):
        resultado = executar_ferramenta("buscar_documentos_internos", {"query": "assunto inexistente"}, self.ctx)
        self.assertFalse(resultado.erro)
        self.assertIn("Nenhum trecho relevante", resultado.conteudo)
        self.assertEqual(resultado.dados_extras["trechos"], [])

    def test_query_ausente_e_argumento_invalido(self):
        resultado = executar_ferramenta("buscar_documentos_internos", {}, self.ctx)
        self.assertTrue(resultado.erro)
        self.assertIn("query", resultado.conteudo)


class TestListarDocumentosDisponiveis(unittest.TestCase):

    def setUp(self):
        self.ctx = ContextoExecucao(tenant_id="senai_labfashion")

    @patch("rag_manager.listar_documentos_indexados", return_value=["manual.pdf", "ficha.docx"])
    def test_lista_documentos_existentes(self, mock_listar):
        resultado = executar_ferramenta("listar_documentos_disponiveis", {}, self.ctx)
        self.assertIn("manual.pdf", resultado.conteudo)
        self.assertIn("ficha.docx", resultado.conteudo)
        mock_listar.assert_called_once_with("senai_labfashion")

    @patch("rag_manager.listar_documentos_indexados", return_value=[])
    def test_sem_documentos_retorna_mensagem_clara(self, mock_listar):
        resultado = executar_ferramenta("listar_documentos_disponiveis", {}, self.ctx)
        self.assertFalse(resultado.erro)
        self.assertIn("Nenhum documento", resultado.conteudo)

    def test_nao_exige_nenhum_parametro(self):
        # A tool não declara properties -- passar {} não deve levantar ErroValidacaoFerramenta.
        with patch("rag_manager.listar_documentos_indexados", return_value=[]):
            resultado = executar_ferramenta("listar_documentos_disponiveis", {}, self.ctx)
        self.assertFalse(resultado.erro)


class TestConsultarResumoPlanilha(unittest.TestCase):

    def test_sem_conversation_id_nao_tenta_carregar(self):
        ctx = ContextoExecucao(tenant_id="senai_labfashion", conversation_id=None)
        with patch("analise_dados.carregar_resumo_estatistico") as mock_carregar:
            resultado = executar_ferramenta("consultar_resumo_planilha", {}, ctx)
            mock_carregar.assert_not_called()
        self.assertIn("Não há planilha", resultado.conteudo)

    @patch("analise_dados.carregar_resumo_estatistico", return_value=None)
    def test_sem_planilha_enviada_retorna_mensagem_clara(self, mock_carregar):
        ctx = ContextoExecucao(tenant_id="senai_labfashion", conversation_id="conv1")
        resultado = executar_ferramenta("consultar_resumo_planilha", {}, ctx)
        self.assertIn("Nenhuma planilha", resultado.conteudo)

    @patch("analise_dados.carregar_resumo_estatistico", return_value={"total_linhas": 50, "agregacoes": {}})
    def test_com_resumo_devolve_json(self, mock_carregar):
        ctx = ContextoExecucao(tenant_id="senai_labfashion", conversation_id="conv1")
        resultado = executar_ferramenta("consultar_resumo_planilha", {}, ctx)
        self.assertIn("total_linhas", resultado.conteudo)
        self.assertIn("50", resultado.conteudo)
        mock_carregar.assert_called_once_with("senai_labfashion", "conv1")


class TestConsultarUnidadesSenai(unittest.TestCase):
    """Mocka `contatos_senai.buscar_unidades` em vez de usar o dado real do módulo (Fase 15,
    Bloco H, Task H1) -- desde que `contatos_senai.py` passou a ter um mecanismo de substituição
    por `contatos_senai_local.py` (dado real, git-ignorado), o dado de verdade varia por máquina.
    Mockar torna o teste determinístico independente de qual arquivo estiver presente no disco."""

    def setUp(self):
        self.ctx = ContextoExecucao(tenant_id="senai_labfashion")
        self._unidades_teste = [
            {"nome": "Unidade Teste Sede", "endereco": "Rua Teste, 1", "telefone": "(11) 1111-1111", "email": "sede@teste.com"},
            *[
                {"nome": f"Escola Teste {i}", "endereco": f"Rua {i}", "telefone": f"(11) 000{i}-0000", "email": f"teste{i}@teste.com"}
                for i in range(11)
            ],
        ]

    @patch("contatos_senai.buscar_unidades")
    def test_sem_termo_lista_todas_as_unidades(self, mock_buscar):
        mock_buscar.return_value = self._unidades_teste
        resultado = executar_ferramenta("consultar_unidades_senai", {}, self.ctx)
        self.assertFalse(resultado.erro)
        self.assertIn("Unidade Teste Sede", resultado.conteudo)
        self.assertGreater(len(resultado.dados_extras["unidades"]), 10)

    @patch("contatos_senai.buscar_unidades")
    def test_filtra_por_cidade_tolerante_a_acento(self, mock_buscar):
        mock_buscar.return_value = [
            {"nome": "Escola Teste Conceição", "endereco": "Av. Central", "telefone": "(11) 4000-0003", "email": "conceicao@teste.com"},
        ]
        resultado = executar_ferramenta("consultar_unidades_senai", {"termo": "conceicao"}, self.ctx)
        self.assertIn("Conceição", resultado.conteudo)
        self.assertNotIn("Itumbiara", resultado.conteudo)
        mock_buscar.assert_called_once_with("conceicao")

    def test_termo_sem_correspondencia_sugere_central(self):
        resultado = executar_ferramenta("consultar_unidades_senai", {"termo": "cidade inexistente xyz"}, self.ctx)
        self.assertFalse(resultado.erro)
        self.assertIn("Central de Atendimento", resultado.conteudo)


if __name__ == "__main__":
    unittest.main()
