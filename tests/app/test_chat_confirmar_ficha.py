# -*- coding: utf-8 -*-
"""Testes de POST /chat/croqui/confirmar para o ramo gerar_ficha_tecnica (Fase 12).

Antes desta fase, esta rota só sabia gerar imagem (Fase 8). Aqui ela ganhou um segundo caminho:
quando `pendente.nome_ferramenta == "gerar_ficha_tecnica"`, em vez de chamar gpt-image-1, cria uma
ficha real em /fichas (mesmo pipeline de POST /fichas) usando a mensagem original do usuário.

`fichas_service.extrair_dados` é sempre mockado -- nenhum destes testes gasta crédito de API real
com extração. A segunda chamada (retomar_apos_confirmacao, síntese textual final) é mockada via
`api.main.OpenAI`, mesmo padrão que TestGerarDesenhoEndpoint em test_api_fichas.py já usa.

Tenant fictício próprio, limpo no tearDown -- mesmo padrão de test_api_fichas.py.
"""

import glob
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import fichas_modelo as fm
import fichas_repo as fr
import tenant_config
from api.main import app
from usage_tracker import incrementar_uso

TENANT_TESTE = "teste_fase12_chat_confirmar_ficha"
ENV_API_KEY = f"{TENANT_TESTE}_OPENAI_API_KEY".upper()


def _limpar_tenant_teste():
    import shutil

    for caminho in glob.glob(os.path.join(fr.DIRETORIO_FICHAS, f"{TENANT_TESTE}_*")):
        if os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        else:
            os.remove(caminho)
    for caminho in glob.glob(os.path.join("tenant_data", f"{TENANT_TESTE}_usage.json*")):
        os.remove(caminho)


def _dados_mockados():
    dados = fm.dados_vazios()
    dados["ficha"]["nome"] = {"valor": "Camisa Social Branca", "origem": fm.ORIGEM_FORNECIDO, "trecho": "camisa social branca"}
    return dados


def _pendente_ficha_tecnica(mensagem_usuario="quero uma ficha técnica de uma camisa social branca"):
    return {
        "tool_call_id": "call_1",
        "nome_ferramenta": "gerar_ficha_tecnica",
        "argumentos": {"resumo_confirmacao": "Uma ficha técnica completa"},
        "resumo_confirmacao": "Uma ficha técnica completa",
        "estilo_croqui": "📐 Desenho Técnico (Flat Sketch)",
        "input_previo": [{"role": "user", "content": mensagem_usuario}],
        "function_call_item": {
            "type": "function_call", "call_id": "call_1", "name": "gerar_ficha_tecnica", "arguments": "{}",
        },
        "instructions": "instrucoes de sistema",
        "mensagem_usuario": mensagem_usuario,
    }


def _resposta_texto_final(texto="Ficha criada! Já pode revisar."):
    from unittest.mock import MagicMock
    return MagicMock(output_text=texto, usage=MagicMock(input_tokens=1, output_tokens=1))


class TestApiConfirmarFichaTecnicaBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tenant_config.TENANT_CONFIG[TENANT_TESTE] = {"nome": "Tenant de Teste (Fase 12)"}
        os.environ[ENV_API_KEY] = "sk-fake-key-de-teste"
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        tenant_config.TENANT_CONFIG.pop(TENANT_TESTE, None)
        os.environ.pop(ENV_API_KEY, None)

    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()

    def _confirmar(self, pendente=None):
        return self.client.post("/chat/croqui/confirmar", json={
            "tenant_id": TENANT_TESTE,
            "confirmado": True,
            "pendente": pendente or _pendente_ficha_tecnica(),
        })


class TestConfirmacaoCriaFichaReal(TestApiConfirmarFichaTecnicaBase):

    @patch("api.main.OpenAI")
    @patch("fichas_service.extrair_dados", return_value=_dados_mockados())
    def test_cria_ficha_de_verdade_e_devolve_id_e_link(self, _mock_extrair, mock_openai_cls):
        mock_openai_cls.return_value.responses.create.return_value = _resposta_texto_final()

        r = self._confirmar()

        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertIsNotNone(corpo["ficha_id"])
        self.assertEqual(corpo["redirecionar_para"], f"/fichas/{corpo['ficha_id']}")
        self.assertIsNone(corpo["imagem_url"])
        self.assertEqual(corpo["resposta"], "Ficha criada! Já pode revisar.")

        ficha_persistida = fr.carregar_ficha(TENANT_TESTE, corpo["ficha_id"])
        self.assertIsNotNone(ficha_persistida)
        self.assertEqual(ficha_persistida["dados"]["ficha"]["nome"]["valor"], "Camisa Social Branca")
        self.assertEqual(ficha_persistida["status"], fm.STATUS_EM_REVISAO)

    @patch("api.main.OpenAI")
    @patch("fichas_service.extrair_dados", return_value=_dados_mockados())
    def test_usa_a_mensagem_original_como_texto_de_origem(self, mock_extrair, mock_openai_cls):
        mock_openai_cls.return_value.responses.create.return_value = _resposta_texto_final()

        r = self._confirmar(_pendente_ficha_tecnica(mensagem_usuario="uma jaqueta jeans oversized azul"))

        self.assertEqual(r.status_code, 200)
        args = mock_extrair.call_args.args
        self.assertEqual(args[1], "uma jaqueta jeans oversized azul")
        ficha_persistida = fr.carregar_ficha(TENANT_TESTE, r.json()["ficha_id"])
        self.assertEqual(ficha_persistida["texto_origem"], "uma jaqueta jeans oversized azul")

    @patch("api.main.OpenAI")
    @patch("fichas_service.extrair_dados", return_value=_dados_mockados())
    def test_incrementa_uso_de_fichas_nao_de_imagens(self, _mock_extrair, mock_openai_cls):
        mock_openai_cls.return_value.responses.create.return_value = _resposta_texto_final()
        self._confirmar()

        from usage_tracker import carregar_uso_do_dia
        uso = carregar_uso_do_dia(TENANT_TESTE)
        self.assertEqual(uso.get("fichas"), 1)
        self.assertEqual(uso.get("imagens", 0), 0)

    def test_confirmado_false_nao_cria_ficha_nem_gasta_chamada(self):
        r = self.client.post("/chat/croqui/confirmar", json={
            "tenant_id": TENANT_TESTE, "confirmado": False, "pendente": _pendente_ficha_tecnica(),
        })
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("ficha_id", r.json())
        self.assertEqual(fr.listar_fichas(TENANT_TESTE), [])


class TestLimiteDiarioDeFichas(TestApiConfirmarFichaTecnicaBase):

    @patch("api.main.OpenAI")
    @patch("fichas_service.extrair_dados", return_value=_dados_mockados())
    def test_limite_diario_bloqueia_com_429_sem_chamar_extracao(self, mock_extrair, mock_openai_cls):
        incrementar_uso(TENANT_TESTE, "fichas", quantidade=30)  # default limite_fichas_dia

        r = self._confirmar()

        self.assertEqual(r.status_code, 429)
        mock_extrair.assert_not_called()
        mock_openai_cls.return_value.responses.create.assert_not_called()
        self.assertEqual(fr.listar_fichas(TENANT_TESTE), [])


class TestSemApiKey(TestApiConfirmarFichaTecnicaBase):

    def test_sem_api_key_configurada_devolve_500(self):
        os.environ.pop(ENV_API_KEY, None)
        try:
            r = self._confirmar()
            self.assertEqual(r.status_code, 500)
        finally:
            os.environ[ENV_API_KEY] = "sk-fake-key-de-teste"


if __name__ == "__main__":
    unittest.main()
