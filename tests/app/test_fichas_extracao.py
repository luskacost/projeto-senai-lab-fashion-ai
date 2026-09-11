# -*- coding: utf-8 -*-
"""Testes de fichas_extracao.py (Fase 11, Task 3).

Client sempre mockado (`MagicMock`, mesmo padrão de tests/app/test_agente_openai.py) -- nenhum
destes testes gasta crédito de API real. Antes de rodar qualquer teste com a API de verdade, o
usuário pediu para ser avisado e dar autorização explícita primeiro.
"""

import json
import unittest
from unittest.mock import MagicMock

import fichas_modelo as fm
import fichas_extracao as fe

TENANT_TESTE = "teste_task3_fichas_extracao"


def _resposta_com_json(dados: dict) -> MagicMock:
    return MagicMock(output_text=json.dumps(dados, ensure_ascii=False))


class TestTextoVazio(unittest.TestCase):
    """Sem texto, não há o que extrair -- e não deveria custar uma chamada de API."""

    def test_texto_vazio_nao_chama_client(self):
        client = MagicMock()
        resultado = fe.extrair_dados(client, "", TENANT_TESTE)
        client.responses.create.assert_not_called()
        self.assertEqual(resultado, fm.dados_vazios())

    def test_texto_so_espacos_nao_chama_client(self):
        client = MagicMock()
        fe.extrair_dados(client, "   \n  ", TENANT_TESTE)
        client.responses.create.assert_not_called()

    def test_texto_none_nao_quebra(self):
        client = MagicMock()
        resultado = fe.extrair_dados(client, None, TENANT_TESTE)
        self.assertEqual(resultado, fm.dados_vazios())


class TestChamadaDaApi(unittest.TestCase):
    """Confirma a forma exata da chamada -- é o contrato de Structured Outputs em modo strict:
    errar qualquer um destes parâmetros faz a API devolver 400 numa chamada real, que só
    descobriríamos gastando crédito."""

    def test_usa_structured_outputs_em_modo_strict(self):
        client = MagicMock()
        client.responses.create.return_value = _resposta_com_json(fm.dados_vazios())

        fe.extrair_dados(client, "camisa preta", TENANT_TESTE)

        kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["text"]["format"]["type"], "json_schema")
        self.assertIs(kwargs["text"]["format"]["strict"], True)
        self.assertEqual(kwargs["text"]["format"]["schema"], fm.SCHEMA_EXTRACAO)

    def test_usa_temperatura_zero(self):
        client = MagicMock()
        client.responses.create.return_value = _resposta_com_json(fm.dados_vazios())
        fe.extrair_dados(client, "camisa preta", TENANT_TESTE)
        self.assertEqual(client.responses.create.call_args.kwargs["temperature"], 0.0)

    def test_texto_do_usuario_vai_no_input(self):
        client = MagicMock()
        client.responses.create.return_value = _resposta_com_json(fm.dados_vazios())
        fe.extrair_dados(client, "camisa social branca manga longa", TENANT_TESTE)
        entrada = client.responses.create.call_args.kwargs["input"]
        self.assertEqual(entrada, [{"role": "user", "content": "camisa social branca manga longa"}])

    def test_usa_o_modelo_de_texto_configurado(self):
        client = MagicMock()
        client.responses.create.return_value = _resposta_com_json(fm.dados_vazios())
        fe.extrair_dados(client, "camisa preta", TENANT_TESTE)
        from rag_config import OPENAI_TEXT_MODEL
        self.assertEqual(client.responses.create.call_args.kwargs["model"], OPENAI_TEXT_MODEL)


class TestParseDaResposta(unittest.TestCase):

    def test_resposta_valida_e_devolvida_como_dict(self):
        dados = fm.dados_vazios()
        dados["ficha"]["nome"] = {"valor": "Camisa Social", "origem": fm.ORIGEM_FORNECIDO, "trecho": "camisa social"}

        client = MagicMock()
        client.responses.create.return_value = _resposta_com_json(dados)

        resultado = fe.extrair_dados(client, "uma camisa social", TENANT_TESTE)
        self.assertEqual(resultado["ficha"]["nome"]["valor"], "Camisa Social")
        self.assertEqual(resultado["ficha"]["nome"]["origem"], fm.ORIGEM_FORNECIDO)

    def test_json_invalido_devolve_dados_vazios(self):
        client = MagicMock()
        client.responses.create.return_value = MagicMock(output_text="isso não é json{{{")
        resultado = fe.extrair_dados(client, "camisa preta", TENANT_TESTE)
        self.assertEqual(resultado, fm.dados_vazios())

    def test_output_text_none_devolve_dados_vazios(self):
        client = MagicMock()
        client.responses.create.return_value = MagicMock(output_text=None)
        resultado = fe.extrair_dados(client, "camisa preta", TENANT_TESTE)
        self.assertEqual(resultado, fm.dados_vazios())

    def test_json_que_nao_e_objeto_devolve_dados_vazios(self):
        client = MagicMock()
        client.responses.create.return_value = MagicMock(output_text=json.dumps(["lista", "solta"]))
        resultado = fe.extrair_dados(client, "camisa preta", TENANT_TESTE)
        self.assertEqual(resultado, fm.dados_vazios())


class TestFalhaDeApi(unittest.TestCase):

    def test_excecao_na_chamada_devolve_dados_vazios(self):
        client = MagicMock()
        client.responses.create.side_effect = RuntimeError("timeout")
        resultado = fe.extrair_dados(client, "camisa preta", TENANT_TESTE)
        self.assertEqual(resultado, fm.dados_vazios())

    def test_excecao_na_chamada_nao_propaga(self):
        client = MagicMock()
        client.responses.create.side_effect = Exception("qualquer erro")
        try:
            fe.extrair_dados(client, "camisa preta", TENANT_TESTE)
        except Exception:
            self.fail("extrair_dados não deveria propagar exceção da API")


if __name__ == "__main__":
    unittest.main()
