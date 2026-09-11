# -*- coding: utf-8 -*-
"""Testes automatizados para geracao_imagem.py (geração de imagem via gpt-image-1).

A busca web (Tavily, buscar_tendencias_web) e a orquestração de tool calling
(chamar_agente/executar_ferramenta_local) que viviam neste módulo foram removidas na Fase 10,
Task 6, junto com os testes que as cobriam -- substituídas por web_search nativo (Task 5) e pelo
motor em agente_openai.py (Task 3-4), já cobertos por tests/app/test_agente_openai.py e
tests/app/test_agente_ferramentas.py.
"""

import unittest
from unittest.mock import MagicMock

from geracao_imagem import chamar_api_geracao_imagem, eh_imagem_gerada, PREFIXO_IMAGEM_GERADA

FAKE_B64 = "ZmFrZS1wbmctYnl0ZXM="  # base64 de "fake-png-bytes", só pra teste


def _mock_client_image(b64_json: str = FAKE_B64) -> MagicMock:
    """Cria um client mockado cujo client.images.generate(...) retorna bytes base64, no mesmo
    formato de resposta usado pelo gpt-image-1 (sucessor do DALL-E 3 na API da OpenAI --
    "dall-e-3" não existe mais como model id)."""
    mock_client = MagicMock()
    mock_client.images.generate.return_value = MagicMock(data=[MagicMock(b64_json=b64_json)])
    return mock_client


class TestChamarApiGeracaoImagem(unittest.TestCase):
    """Fase 9, Bloco A: geração de imagem migrou do Pollinations (URL local, sem chamada real)
    para gpt-image-1 (chamada síncrona de verdade à API da OpenAI, retorna base64 -- não URL)."""

    def test_sucesso_retorna_data_uri_com_base64_da_resposta(self):
        mock_client = _mock_client_image(FAKE_B64)
        resultado = chamar_api_geracao_imagem(mock_client, "vestido midi floral", "senai_labfashion")
        self.assertEqual(resultado, PREFIXO_IMAGEM_GERADA + FAKE_B64)
        self.assertTrue(eh_imagem_gerada(resultado))
        mock_client.images.generate.assert_called_once()
        self.assertEqual(mock_client.images.generate.call_args.kwargs["model"], "gpt-image-1")
        self.assertEqual(mock_client.images.generate.call_args.kwargs["prompt"], "vestido midi floral")

    def test_falha_na_api_retorna_none_sem_levantar_excecao(self):
        mock_client = MagicMock()
        mock_client.images.generate.side_effect = Exception("content_policy_violation")
        resultado = chamar_api_geracao_imagem(mock_client, "prompt qualquer", "senai_labfashion")
        self.assertIsNone(resultado)

    def test_eh_imagem_gerada_rejeita_outros_valores(self):
        self.assertFalse(eh_imagem_gerada(None))
        self.assertFalse(eh_imagem_gerada("Imagem gerada com sucesso."))
        self.assertFalse(eh_imagem_gerada("https://exemplo.com/nao-e-imagem-gerada.png"))


if __name__ == "__main__":
    unittest.main()
