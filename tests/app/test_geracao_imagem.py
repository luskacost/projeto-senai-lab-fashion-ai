# -*- coding: utf-8 -*-
"""Testes automatizados para geracao_imagem.py (busca real na web via Tavily, croqui)."""

import json
import unittest
from unittest.mock import MagicMock, patch

from geracao_imagem import (
    buscar_tendencias_web,
    chamar_agente,
    chamar_api_geracao_imagem,
    eh_imagem_gerada,
    executar_ferramenta_local,
    PREFIXO_IMAGEM_GERADA,
)

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

        texto, fontes = buscar_tendencias_web("cores tendência 2027", "senai_labfashion")

        mock_secret.assert_called_once_with("senai_labfashion", "TAVILY_API_KEY")
        self.assertIn("Cores tendência 2027", texto)
        self.assertIn("https://exemplo.com/cores-2027", texto)
        self.assertIn("Relatório Pantone", texto)
        self.assertIn("cite a URL", texto)

        # Fontes estruturadas (usadas por _chat_via_agente para fontes_consultadas/trechos_consultados)
        self.assertEqual(len(fontes), 2)
        self.assertEqual(fontes[0]["titulo"], "Cores tendência 2027")
        self.assertEqual(fontes[0]["url"], "https://exemplo.com/cores-2027")
        self.assertEqual(fontes[1]["titulo"], "Relatório Pantone")

    @patch("geracao_imagem.obter_secret_tenant", return_value="")
    def test_sem_api_key_retorna_erro_sem_chamar_rede(self, mock_secret):
        with patch("geracao_imagem.requests.post") as mock_post:
            texto, fontes = buscar_tendencias_web("qualquer coisa", "senai_labfashion")
            mock_post.assert_not_called()
        self.assertIn("[Erro]", texto)
        self.assertIn("TAVILY_API_KEY", texto)
        self.assertEqual(fontes, [])

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post", side_effect=Exception("timeout de rede"))
    def test_falha_de_rede_retorna_erro_sem_quebrar(self, mock_post, mock_secret):
        texto, fontes = buscar_tendencias_web("cores tendência 2027", "senai_labfashion")
        self.assertIn("[Erro]", texto)
        self.assertIn("timeout de rede", texto)
        self.assertEqual(fontes, [])

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post")
    def test_sem_resultados_retorna_mensagem_clara(self, mock_post, mock_secret):
        mock_resposta = MagicMock()
        mock_resposta.json.return_value = {"results": []}
        mock_resposta.raise_for_status.return_value = None
        mock_post.return_value = mock_resposta

        texto, fontes = buscar_tendencias_web("assunto sem resultado nenhum", "senai_labfashion")
        self.assertIn("Nenhum resultado", texto)
        self.assertEqual(fontes, [])


class TestExecutarFerramentaLocal(unittest.TestCase):
    """Confirma que o dispatcher de ferramentas continua funcionando para os 3 casos (regressão)."""

    def test_ferramenta_desconhecida_retorna_erro(self):
        resultado = executar_ferramenta_local(MagicMock(), "ferramenta_inexistente", {}, "senai_labfashion")
        self.assertIn("não reconhecida", resultado)

    def test_gerar_imagem_croqui_continua_funcionando(self):
        mock_client = _mock_client_image(FAKE_B64)
        resultado = executar_ferramenta_local(
            mock_client, "gerar_imagem_croqui", {"prompt_visual": "vestido midi floral"}, "senai_labfashion"
        )
        self.assertEqual(resultado, PREFIXO_IMAGEM_GERADA + FAKE_B64)

    def test_gerar_imagem_croqui_com_falha_retorna_mensagem_de_erro(self):
        mock_client = MagicMock()
        mock_client.images.generate.side_effect = Exception("falha na API")
        resultado = executar_ferramenta_local(
            mock_client, "gerar_imagem_croqui", {"prompt_visual": "vestido midi floral"}, "senai_labfashion"
        )
        self.assertIn("[Erro]", resultado)

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post")
    def test_dispatcher_encaminha_para_busca_tendencias(self, mock_post, mock_secret):
        mock_resposta = MagicMock()
        mock_resposta.json.return_value = {"results": [{"title": "T", "url": "https://x.com", "content": "c"}]}
        mock_resposta.raise_for_status.return_value = None
        mock_post.return_value = mock_resposta

        resultado = executar_ferramenta_local(
            MagicMock(), "buscar_tendencias_web", {"query": "tendências outono"}, "senai_labfashion"
        )
        self.assertIn("https://x.com", resultado)


class TestChamarAgenteComBuscaWeb(unittest.TestCase):
    """Fluxo completo de tool-calling (2 chamadas ao client) com a tool buscar_tendencias_web."""

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post")
    def test_chamar_agente_retorna_fontes_estruturadas_da_busca(self, mock_post, mock_secret):
        mock_tavily_resp = MagicMock()
        mock_tavily_resp.json.return_value = {
            "results": [{"title": "Fonte X", "url": "https://x.com", "content": "trecho relevante"}]
        }
        mock_tavily_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_tavily_resp

        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.function.name = "buscar_tendencias_web"
        mock_tool_call.function.arguments = json.dumps({"query": "tendências 2027"})

        mock_msg_com_tool = MagicMock()
        mock_msg_com_tool.content = ""
        mock_msg_com_tool.tool_calls = [mock_tool_call]

        mock_msg_final = MagicMock()
        mock_msg_final.content = "Resposta final citando https://x.com"
        mock_msg_final.tool_calls = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=mock_msg_com_tool)]),
            MagicMock(choices=[MagicMock(message=mock_msg_final)]),
        ]

        agente_config = {"tools": [{"type": "function", "function": {"name": "buscar_tendencias_web"}}]}
        texto, imagem_url, usou_fallback, pendente, fontes = chamar_agente(
            mock_client, agente_config, [{"role": "user", "content": "quais as tendências?"}], "senai_labfashion"
        )

        self.assertEqual(texto, "Resposta final citando https://x.com")
        self.assertIsNone(imagem_url)
        self.assertFalse(usou_fallback)
        self.assertIsNone(pendente)
        self.assertEqual(len(fontes), 1)
        self.assertEqual(fontes[0]["url"], "https://x.com")
        self.assertEqual(fontes[0]["titulo"], "Fonte X")

    def test_sem_tool_calls_retorna_fontes_vazias(self):
        mock_msg = MagicMock()
        mock_msg.content = "Resposta direta sem ferramentas."
        mock_msg.tool_calls = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=mock_msg)])

        texto, imagem_url, usou_fallback, pendente, fontes = chamar_agente(
            mock_client, {"tools": None}, [{"role": "user", "content": "oi"}], "senai_labfashion"
        )

        self.assertEqual(texto, "Resposta direta sem ferramentas.")
        self.assertEqual(fontes, [])
        self.assertIsNone(pendente)

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post")
    def test_modelo_chama_ferramenta_de_novo_na_segunda_rodada(self, mock_post, mock_secret):
        # Regressão: encontrado em teste manual real -- a 2a chamada ao Groq nao repassava
        # "tools", e quando o modelo decidia chamar a ferramenta de novo (refinando a busca), a
        # Groq rejeitava com 400 "Tool choice is none, but model called a tool". Agora o loop
        # permite ate 3 rodadas passando tools=tools/tool_choice="auto" em cada uma.
        mock_tavily_resp = MagicMock()
        mock_tavily_resp.json.return_value = {
            "results": [{"title": "Fonte", "url": "https://exemplo.com", "content": "trecho"}]
        }
        mock_tavily_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_tavily_resp

        def _fazer_tool_call(query):
            tc = MagicMock()
            tc.id = f"call_{query}"
            tc.function.name = "buscar_tendencias_web"
            tc.function.arguments = json.dumps({"query": query})
            return tc

        msg_rodada_1 = MagicMock(content="", tool_calls=[_fazer_tool_call("busca inicial")])
        msg_rodada_2 = MagicMock(content="", tool_calls=[_fazer_tool_call("busca refinada")])
        msg_rodada_3 = MagicMock(content="Resposta final após refinar a busca.", tool_calls=None)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=msg_rodada_1)]),
            MagicMock(choices=[MagicMock(message=msg_rodada_2)]),
            MagicMock(choices=[MagicMock(message=msg_rodada_3)]),
        ]

        agente_config = {"tools": [{"type": "function", "function": {"name": "buscar_tendencias_web"}}]}
        texto, imagem_url, usou_fallback, pendente, fontes = chamar_agente(
            mock_client, agente_config, [{"role": "user", "content": "tendências?"}], "senai_labfashion"
        )

        self.assertEqual(texto, "Resposta final após refinar a busca.")
        self.assertEqual(len(fontes), 2)  # uma busca por rodada, 2 rodadas com tool call
        self.assertEqual(mock_client.chat.completions.create.call_count, 3)
        # A 2a chamada (rodada 1 -> 2) precisa repassar tools, senão reproduz o bug original
        segunda_chamada_kwargs = mock_client.chat.completions.create.call_args_list[1].kwargs
        self.assertIsNotNone(segunda_chamada_kwargs.get("tools"))
        self.assertEqual(segunda_chamada_kwargs.get("tool_choice"), "auto")

    @patch("geracao_imagem.obter_secret_tenant", return_value="chave-tavily-fake")
    @patch("geracao_imagem.requests.post")
    def test_rede_de_seguranca_nao_propaga_erro_se_groq_falhar_apos_tool_call(self, mock_post, mock_secret):
        mock_tavily_resp = MagicMock()
        mock_tavily_resp.json.return_value = {
            "results": [{"title": "Fonte", "url": "https://exemplo.com", "content": "trecho"}]
        }
        mock_tavily_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_tavily_resp

        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.function.name = "buscar_tendencias_web"
        mock_tool_call.function.arguments = json.dumps({"query": "tendências"})
        msg_com_tool = MagicMock(content="", tool_calls=[mock_tool_call])

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=msg_com_tool)]),
            Exception("Tool choice is none, but model called a tool"),
        ]

        agente_config = {"tools": [{"type": "function", "function": {"name": "buscar_tendencias_web"}}]}
        # Não deve levantar exceção -- degrada graciosamente em vez de propagar um 500.
        texto, imagem_url, usou_fallback, pendente, fontes = chamar_agente(
            mock_client, agente_config, [{"role": "user", "content": "tendências?"}], "senai_labfashion"
        )
        self.assertIsInstance(texto, str)
        self.assertEqual(len(fontes), 1)


if __name__ == "__main__":
    unittest.main()
