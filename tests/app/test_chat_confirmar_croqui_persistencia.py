# -*- coding: utf-8 -*-
"""POST /chat/croqui/confirmar persiste o croqui gerado na galeria (Fase 14, Bloco G, Task 14).

Antes desta task, a imagem gerada só ia para `imagem_url` na resposta -- existia apenas como data
URI dentro do histórico da conversa, sem nenhuma cópia em `croquis_repo`. Cobre: o croqui aparece
em `croquis_repo.listar_croquis` depois da confirmação, a resposta HTTP traz `croqui_id`, e uma
falha ao persistir (best-effort) não derruba a resposta que o usuário já pagou por ela.

`fichas_desenho`/`moderacao` não entram aqui -- só o ramo `gerar_imagem_croqui` de
`/chat/croqui/confirmar`, mockando `api.main.validar_prompt_imagem` (moderação) e
`api.main.OpenAI` (geração via gpt-image-1). Tenant fictício próprio, limpo no tearDown.
"""

import base64
import glob
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import croquis_repo as cr
import tenant_config
from api.main import app

TENANT_TESTE = "teste_fase14_confirmar_croqui"
ENV_API_KEY = f"{TENANT_TESTE}_OPENAI_API_KEY".upper()
PNG_FAKE = b"\x89PNG\r\n\x1a\n" + b"conteudo minimo"


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(cr.DIRETORIO_CROQUIS, f"{TENANT_TESTE}_*")):
        os.remove(caminho)
    for caminho in glob.glob(os.path.join("tenant_data", f"{TENANT_TESTE}_usage.json*")):
        os.remove(caminho)


def _resposta_imagem_ok():
    item = MagicMock(b64_json=base64.b64encode(PNG_FAKE).decode("ascii"))
    return MagicMock(data=[item])


def _resposta_texto_final(texto="Ficou ótimo! Aqui está o croqui."):
    return MagicMock(output_text=texto, usage=MagicMock(input_tokens=1, output_tokens=1))


def _pendente_gerar_imagem(resumo="Um vestido midi floral"):
    return {
        "tool_call_id": "call_1",
        "nome_ferramenta": "gerar_imagem_croqui",
        "argumentos": {"prompt_visual": "a floral midi dress, front view", "resumo_confirmacao": resumo},
        "prompt_visual": "a floral midi dress, front view",
        "resumo_confirmacao": resumo,
        "estilo_croqui": "🎨 Ilustração de Moda",
        "input_previo": [{"role": "user", "content": "crie um croqui de vestido midi floral"}],
        "function_call_item": {
            "type": "function_call", "call_id": "call_1", "name": "gerar_imagem_croqui", "arguments": "{}",
        },
        "instructions": "instrucoes de sistema",
    }


class TestConfirmarCroquiPersistencia(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tenant_config.TENANT_CONFIG[TENANT_TESTE] = {"nome": "Tenant de Teste (Fase 14)"}
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
            "pendente": pendente or _pendente_gerar_imagem(),
        })

    @patch("api.main.OpenAI")
    @patch("api.main.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_resposta_traz_croqui_id(self, _mod, mock_openai_cls):
        mock_openai_cls.return_value.images.generate.return_value = _resposta_imagem_ok()
        mock_openai_cls.return_value.responses.create.return_value = _resposta_texto_final()

        r = self._confirmar()

        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertIsNotNone(corpo["croqui_id"])
        self.assertIsNotNone(corpo["imagem_url"])

    @patch("api.main.OpenAI")
    @patch("api.main.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_croqui_aparece_na_galeria_com_o_png_correto(self, _mod, mock_openai_cls):
        mock_openai_cls.return_value.images.generate.return_value = _resposta_imagem_ok()
        mock_openai_cls.return_value.responses.create.return_value = _resposta_texto_final()

        r = self._confirmar(_pendente_gerar_imagem(resumo="Uma jaqueta jeans oversized"))
        croqui_id = r.json()["croqui_id"]

        listagem = cr.listar_croquis(TENANT_TESTE)
        self.assertEqual([e["id"] for e in listagem], [croqui_id])
        self.assertEqual(listagem[0]["resumo"], "Uma jaqueta jeans oversized")
        self.assertEqual(listagem[0]["estilo"], "🎨 Ilustração de Moda")

        with open(cr.caminho_croqui(TENANT_TESTE, croqui_id), "rb") as f:
            self.assertEqual(f.read(), PNG_FAKE)

    @patch("api.main.OpenAI")
    @patch("api.main.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    @patch("api.main.salvar_croqui", side_effect=OSError("disco cheio"))
    def test_falha_ao_persistir_nao_derruba_a_resposta(self, _mock_salvar, _mod, mock_openai_cls):
        # Best-effort: a imagem já foi gerada e cobrada -- uma falha de disco na galeria não pode
        # virar 500 nem descartar a resposta que o usuário já pagou por ela.
        mock_openai_cls.return_value.images.generate.return_value = _resposta_imagem_ok()
        mock_openai_cls.return_value.responses.create.return_value = _resposta_texto_final()

        r = self._confirmar()

        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertIsNone(corpo["croqui_id"])
        self.assertIsNotNone(corpo["imagem_url"])

    @patch("api.main.OpenAI")
    @patch("api.main.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_confirmado_false_nao_persiste_nada(self, _mod, mock_openai_cls):
        r = self.client.post("/chat/croqui/confirmar", json={
            "tenant_id": TENANT_TESTE, "confirmado": False, "pendente": _pendente_gerar_imagem(),
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(cr.listar_croquis(TENANT_TESTE), [])
        mock_openai_cls.return_value.images.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
