# -*- coding: utf-8 -*-
"""Testes do motor do agente sobre a Responses API (agente_openai.py, Fase 10, Bloco B).

Ainda não plugado em nenhuma rota (ver docstring do módulo) -- estes testes validam o motor
isoladamente, com o client da OpenAI mockado no mesmo padrão de tests/app/test_geracao_imagem.py.
"""

import unittest
from unittest.mock import MagicMock, patch

from agente_ferramentas import ContextoExecucao
from agente_openai import chamar_agente, montar_input_historico, retomar_apos_confirmacao


def _mensagem_item(texto: str, anotacoes=None):
    """Cria um item de resposta tipo "message" com um único bloco output_text."""
    conteudo = MagicMock(type="output_text", text=texto, annotations=anotacoes or [])
    item = MagicMock(type="message", content=[conteudo])
    item.model_dump.return_value = {"type": "message", "content": [{"type": "output_text", "text": texto}]}
    return item


def _function_call_item(call_id: str, nome: str, argumentos_json: str):
    # "name" é um kwarg reservado do construtor de MagicMock (define o repr do mock, não um
    # atributo) -- precisa ser atribuído depois de criado, não passado no construtor.
    item = MagicMock(type="function_call", call_id=call_id, arguments=argumentos_json)
    item.name = nome
    item.model_dump.return_value = {
        "type": "function_call", "call_id": call_id, "name": nome, "arguments": argumentos_json,
    }
    return item


def _resposta(output_items, texto_final: str):
    return MagicMock(output=output_items, output_text=texto_final)


class TestMontarInputHistorico(unittest.TestCase):

    def test_sem_historico_usa_so_a_mensagem_atual(self):
        itens = montar_input_historico("oi", None)
        self.assertEqual(itens, [{"role": "user", "content": "oi"}])

    def test_com_historico_converte_role_ia_para_assistant(self):
        m1 = MagicMock(role="user", content="pergunta")
        m2 = MagicMock(role="IA", content="resposta anterior")
        itens = montar_input_historico("ignorado", [m1, m2])
        self.assertEqual(itens, [
            {"role": "user", "content": "pergunta"},
            {"role": "assistant", "content": "resposta anterior"},
        ])


class TestRespostaDireta(unittest.TestCase):
    """Cenário 1 da Etapa 9: pergunta que não precisa de nenhuma ferramenta."""

    def test_sem_tool_calls_retorna_texto_direto(self):
        client = MagicMock()
        client.responses.create.return_value = _resposta([], "Resposta direta sem ferramentas.")

        resultado = chamar_agente(
            client, "instrucoes", None, [{"role": "user", "content": "oi"}],
            ContextoExecucao(tenant_id="senai_labfashion"),
        )

        self.assertEqual(resultado.texto, "Resposta direta sem ferramentas.")
        self.assertIsNone(resultado.pendente_confirmacao)
        self.assertEqual(resultado.fontes, [])
        self.assertFalse(resultado.usou_web_search)
        kwargs = client.responses.create.call_args.kwargs
        self.assertIsNone(kwargs["tools"])


class TestWebSearch(unittest.TestCase):
    """Cenário 2: pergunta que exige informação atual -- web_search nativo."""

    def test_web_search_call_e_citacoes_sao_capturadas(self):
        client = MagicMock()
        item_busca = MagicMock(type="web_search_call")
        item_msg = _mensagem_item(
            "Segundo a Pantone, a cor de 2026 e X.",
            anotacoes=[MagicMock(type="url_citation", title="Pantone", url="https://pantone.com/x", start_index=0, end_index=10)],
        )
        client.responses.create.return_value = _resposta([item_busca, item_msg], "Segundo a Pantone, a cor de 2026 e X.")

        resultado = chamar_agente(
            client, "instrucoes", ["buscar_documentos_internos"], [{"role": "user", "content": "cores 2026"}],
            ContextoExecucao(tenant_id="senai_labfashion"), usar_web_search=True,
        )

        self.assertTrue(resultado.usou_web_search)
        self.assertEqual(len(resultado.fontes), 1)
        self.assertEqual(resultado.fontes[0]["titulo"], "Pantone")
        self.assertEqual(resultado.fontes[0]["url"], "https://pantone.com/x")
        kwargs = client.responses.create.call_args.kwargs
        self.assertTrue(any(t.get("type") == "web_search" for t in kwargs["tools"]))


class TestFerramentaInternaSemConfirmacao(unittest.TestCase):
    """Cenário 3/4: pergunta que exige consulta a dado interno / múltiplas ferramentas."""

    @patch("agente_openai.executar_ferramenta")
    def test_executa_ferramenta_e_continua_ate_resposta_final(self, mock_executar):
        from agente_ferramentas import ResultadoFerramenta

        mock_executar.return_value = ResultadoFerramenta(conteudo="Escola SENAI Catalão: (64) 3445-1700")

        client = MagicMock()
        call = _function_call_item("call_1", "consultar_unidades_senai", '{"termo": "catalao"}')
        client.responses.create.side_effect = [
            _resposta([call], ""),
            _resposta([], "O telefone da unidade de Catalão é (64) 3445-1700."),
        ]

        resultado = chamar_agente(
            client, "instrucoes", ["consultar_unidades_senai"], [{"role": "user", "content": "telefone catalao?"}],
            ContextoExecucao(tenant_id="senai_labfashion"),
        )

        self.assertEqual(resultado.texto, "O telefone da unidade de Catalão é (64) 3445-1700.")
        self.assertEqual(client.responses.create.call_count, 2)
        segunda_chamada = client.responses.create.call_args_list[1].kwargs
        # A rodada seguinte precisa carregar o function_call original + o output executado.
        tipos_input = [item.get("type") for item in segunda_chamada["input"] if isinstance(item, dict)]
        self.assertIn("function_call_output", tipos_input)


class TestConfirmacaoObrigatoria(unittest.TestCase):
    """Ferramentas caras param o loop e devolvem pendente em vez de executar."""

    def test_gerar_imagem_croqui_devolve_pendente_sem_executar(self):
        client = MagicMock()
        call = _function_call_item(
            "call_1", "gerar_imagem_croqui",
            '{"prompt_visual": "floral midi dress", "resumo_confirmacao": "Um vestido midi floral"}',
        )
        client.responses.create.return_value = _resposta([call], "")

        with patch("agente_openai.executar_ferramenta") as mock_executar:
            resultado = chamar_agente(
                client, "instrucoes", ["gerar_imagem_croqui"], [{"role": "user", "content": "quero um croqui"}],
                ContextoExecucao(tenant_id="senai_labfashion"),
            )
            mock_executar.assert_not_called()

        self.assertIsNone(resultado.texto)
        self.assertIsNotNone(resultado.pendente_confirmacao)
        pendente = resultado.pendente_confirmacao
        self.assertEqual(pendente["nome_ferramenta"], "gerar_imagem_croqui")
        self.assertEqual(pendente["prompt_visual"], "floral midi dress")
        self.assertEqual(pendente["resumo_confirmacao"], "Um vestido midi floral")
        self.assertEqual(pendente["tool_call_id"], "call_1")
        self.assertIn("function_call_item", pendente)
        self.assertIn("input_previo", pendente)


class TestRetomarAposConfirmacao(unittest.TestCase):

    def test_monta_input_com_function_call_e_output_e_devolve_texto(self):
        client = MagicMock()
        client.responses.create.return_value = MagicMock(output_text="Ficha técnica completa: ...")

        pendente = {
            "input_previo": [{"role": "user", "content": "quero uma ficha técnica"}],
            "function_call_item": {"type": "function_call", "call_id": "call_1", "name": "gerar_ficha_tecnica", "arguments": "{}"},
            "tool_call_id": "call_1",
        }

        texto = retomar_apos_confirmacao(client, "instrucoes", pendente, "Desenho técnico gerado (sucesso).")

        self.assertEqual(texto, "Ficha técnica completa: ...")
        kwargs = client.responses.create.call_args.kwargs
        self.assertNotIn("tools", kwargs)
        tipos = [item.get("type") for item in kwargs["input"]]
        self.assertIn("function_call", tipos)
        self.assertIn("function_call_output", tipos)
        saida = next(i for i in kwargs["input"] if i.get("type") == "function_call_output")
        self.assertEqual(saida["output"], "Desenho técnico gerado (sucesso).")
        self.assertEqual(saida["call_id"], "call_1")


class TestFalhaWebSearch(unittest.TestCase):
    """Cenário 6: falha da Web Search (a própria chamada com tools falha)."""

    def test_falha_com_tools_faz_fallback_sem_tools(self):
        client = MagicMock()
        client.responses.create.side_effect = [
            Exception("tool use not supported for this model"),
            MagicMock(output_text="Resposta sem busca, de conhecimento geral."),
        ]

        resultado = chamar_agente(
            client, "instrucoes", None, [{"role": "user", "content": "oi"}],
            ContextoExecucao(tenant_id="senai_labfashion"), usar_web_search=True,
        )

        self.assertEqual(resultado.texto, "Resposta sem busca, de conhecimento geral.")
        self.assertEqual(client.responses.create.call_count, 2)
        segunda_chamada = client.responses.create.call_args_list[1].kwargs
        self.assertNotIn("tools", segunda_chamada)

    def test_falha_nao_relacionada_a_tools_propaga(self):
        client = MagicMock()
        client.responses.create.side_effect = Exception("insufficient_quota")

        with self.assertRaises(Exception):
            chamar_agente(
                client, "instrucoes", None, [{"role": "user", "content": "oi"}],
                ContextoExecucao(tenant_id="senai_labfashion"),
            )


class TestFalhaFerramentaInterna(unittest.TestCase):
    """Cenário 7: falha de uma tool interna -- não deve propagar exceção nem travar o agente."""

    @patch("agente_openai.executar_ferramenta")
    def test_erro_ao_continuar_apos_ferramenta_degrada_sem_excecao(self, mock_executar):
        from agente_ferramentas import ResultadoFerramenta

        mock_executar.return_value = ResultadoFerramenta(conteudo="[Erro] falhou", erro=True)

        client = MagicMock()
        call = _function_call_item("call_1", "consultar_resumo_planilha", "{}")
        client.responses.create.side_effect = [
            _resposta([call], ""),
            Exception("erro de rede na segunda chamada"),
        ]

        resultado = chamar_agente(
            client, "instrucoes", ["consultar_resumo_planilha"], [{"role": "user", "content": "resumo?"}],
            ContextoExecucao(tenant_id="senai_labfashion"),
        )

        self.assertIsInstance(resultado.texto, str)
        self.assertIn("Não consegui", resultado.texto)


class TestLimiteDeRodadas(unittest.TestCase):
    """Cenário 12 (adaptado): o modelo insiste em chamar ferramentas além do limite de segurança."""

    @patch("agente_openai.executar_ferramenta")
    def test_excede_max_rodadas_encerra_com_texto_disponivel(self, mock_executar):
        from agente_ferramentas import ResultadoFerramenta
        from agente_openai import MAX_RODADAS_FERRAMENTA

        mock_executar.return_value = ResultadoFerramenta(conteudo="ok")

        client = MagicMock()
        # Uma function_call por rodada, sempre a mesma ferramenta -- o modelo nunca para de chamar.
        respostas = [
            _resposta([_function_call_item(f"call_{i}", "consultar_resumo_planilha", "{}")], "")
            for i in range(MAX_RODADAS_FERRAMENTA + 2)
        ]
        client.responses.create.side_effect = respostas

        resultado = chamar_agente(
            client, "instrucoes", ["consultar_resumo_planilha"], [{"role": "user", "content": "resumo?"}],
            ContextoExecucao(tenant_id="senai_labfashion"),
        )

        self.assertIsInstance(resultado.texto, str)
        self.assertLessEqual(client.responses.create.call_count, MAX_RODADAS_FERRAMENTA + 2)


if __name__ == "__main__":
    unittest.main()
