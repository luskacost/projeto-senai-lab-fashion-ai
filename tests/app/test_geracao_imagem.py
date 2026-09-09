# -*- coding: utf-8 -*-
"""Testes automatizados para geracao_imagem.py (busca real na web via Tavily, croqui)."""

import unittest
from unittest.mock import MagicMock, patch

from geracao_imagem import buscar_tendencias_web, executar_ferramenta_local


class TestBuscarTendenciasWeb(unittest.TestCase):
    """Fase 7, Bloco C: modo Tendências deixa de alucinar e passa a buscar de verdade (Tavily)."""

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post")
    def test_busca_com_sucesso_formata_titulo_url_trecho(self, mock_post, mock_secret):
        mock_resposta = MagicMock()
        mock_resposta.json.return_value = {
            "results": [
                {"title": "Cores tendência 2027", "url": "https://exemplo.com/cores-2027", "content": "Texto sobre tendências de cor."},
                {"title": "Relatório Pantone", "url": "https://exemplo.com/pantone", "content": "Outro trecho relevante."},
            ]
        }
        mock_resposta.raise_for_status.return_value = None
        mock_post.return_value = mock_resposta

        resultado = buscar_tendencias_web("cores tendência 2027", "senai_labfashion")

        mock_secret.assert_called_once_with("senai_labfashion", "TAVILY_API_KEY")
        self.assertIn("Cores tendência 2027", resultado)
        self.assertIn("https://exemplo.com/cores-2027", resultado)
        self.assertIn("Relatório Pantone", resultado)
        self.assertIn("cite a URL", resultado)

    @patch("geracao_imagem.obter_secret_tenant", return_value="")
    def test_sem_api_key_retorna_erro_sem_chamar_rede(self, mock_secret):
        with patch("geracao_imagem.requests.post") as mock_post:
            resultado = buscar_tendencias_web("qualquer coisa", "senai_labfashion")
            mock_post.assert_not_called()
        self.assertIn("[Erro]", resultado)
        self.assertIn("TAVILY_API_KEY", resultado)

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post", side_effect=Exception("timeout de rede"))
    def test_falha_de_rede_retorna_erro_sem_quebrar(self, mock_post, mock_secret):
        resultado = buscar_tendencias_web("cores tendência 2027", "senai_labfashion")
        self.assertIn("[Erro]", resultado)
        self.assertIn("timeout de rede", resultado)

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post")
    def test_sem_resultados_retorna_mensagem_clara(self, mock_post, mock_secret):
        mock_resposta = MagicMock()
        mock_resposta.json.return_value = {"results": []}
        mock_resposta.raise_for_status.return_value = None
        mock_post.return_value = mock_resposta

        resultado = buscar_tendencias_web("assunto sem resultado nenhum", "senai_labfashion")
        self.assertIn("Nenhum resultado", resultado)


class TestExecutarFerramentaLocal(unittest.TestCase):
    """Confirma que o dispatcher de ferramentas continua funcionando para os 3 casos (regressão)."""

    def test_ferramenta_desconhecida_retorna_erro(self):
        resultado = executar_ferramenta_local("ferramenta_inexistente", {}, "senai_labfashion")
        self.assertIn("não reconhecida", resultado)

    def test_gerar_imagem_croqui_continua_funcionando(self):
        resultado = executar_ferramenta_local(
            "gerar_imagem_croqui", {"prompt_visual": "vestido midi floral"}, "senai_labfashion"
        )
        self.assertTrue(resultado.startswith("https://image.pollinations.ai/prompt/"))

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post")
    def test_dispatcher_encaminha_para_busca_tendencias(self, mock_post, mock_secret):
        mock_resposta = MagicMock()
        mock_resposta.json.return_value = {"results": [{"title": "T", "url": "https://x.com", "content": "c"}]}
        mock_resposta.raise_for_status.return_value = None
        mock_post.return_value = mock_resposta

        resultado = executar_ferramenta_local(
            "buscar_tendencias_web", {"query": "tendências outono"}, "senai_labfashion"
        )
        self.assertIn("https://x.com", resultado)


if __name__ == "__main__":
    unittest.main()
