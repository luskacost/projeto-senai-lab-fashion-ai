# -*- coding: utf-8 -*-
"""Testes de fichas_desenho.py (Fase 11, Task 15).

`gerar_imagem_desenho` é sempre exercitado com client mockado (`MagicMock`) -- nenhum destes
testes faz uma chamada real de API. Usa um tenant/ficha fictícios e limpa o diretório da ficha no
tearDown.
"""

import base64
import os
import shutil
import unittest
from unittest.mock import MagicMock

import fichas_desenho as fdz
import fichas_repo as fr

TENANT_TESTE = "teste_task15_desenho"
FICHA_TESTE = "88888888-8888-8888-8888-888888888888"

PNG_MINIMO = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _resposta_com_imagem(conteudo: bytes = PNG_MINIMO):
    item = MagicMock(b64_json=base64.b64encode(conteudo).decode("ascii"))
    return MagicMock(data=[item])


class TestFichaDesenhoBase(unittest.TestCase):
    def setUp(self):
        self._limpar()

    def tearDown(self):
        self._limpar()

    def _limpar(self):
        diretorio = fr._dir_ficha(TENANT_TESTE, FICHA_TESTE)
        if os.path.isdir(diretorio):
            shutil.rmtree(diretorio, ignore_errors=True)


class TestGerarImagemDesenho(TestFichaDesenhoBase):

    def test_sucesso_devolve_bytes_crus(self):
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()

        resultado = fdz.gerar_imagem_desenho(client, "camisa branca, desenho tecnico", TENANT_TESTE)

        self.assertEqual(resultado, PNG_MINIMO)
        self.assertIsInstance(resultado, bytes)

    def test_nao_devolve_data_uri(self):
        # A diferença central em relação a geracao_imagem.chamar_api_geracao_imagem(): esta função
        # nunca deve devolver a string "data:image/png;base64,...".
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()
        resultado = fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        self.assertNotIsInstance(resultado, str)

    def test_usa_o_modelo_gpt_image_1(self):
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()
        fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        self.assertEqual(client.images.generate.call_args.kwargs["model"], "gpt-image-1")

    def test_tamanho_padrao_e_retrato(self):
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()
        fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        self.assertEqual(client.images.generate.call_args.kwargs["size"], "1024x1536")

    def test_tamanho_customizado_e_repassado(self):
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()
        fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE, tamanho="1024x1024")
        self.assertEqual(client.images.generate.call_args.kwargs["size"], "1024x1024")

    def test_falha_na_api_devolve_none(self):
        client = MagicMock()
        client.images.generate.side_effect = RuntimeError("falha de rede")
        resultado = fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        self.assertIsNone(resultado)

    def test_falha_na_api_nao_propaga_excecao(self):
        client = MagicMock()
        client.images.generate.side_effect = Exception("qualquer erro")
        try:
            fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        except Exception:
            self.fail("gerar_imagem_desenho não deveria propagar exceção da API")


class TestPersistencia(TestFichaDesenhoBase):

    def test_salvar_e_recuperar(self):
        caminho = fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 1, PNG_MINIMO)
        self.assertTrue(os.path.exists(caminho))
        with open(caminho, "rb") as f:
            self.assertEqual(f.read(), PNG_MINIMO)

    def test_nome_do_arquivo_inclui_a_versao(self):
        caminho = fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 3, PNG_MINIMO)
        self.assertTrue(caminho.endswith("desenho_v3.png"))

    def test_versoes_diferentes_nao_se_sobrescrevem(self):
        # É o que permite comparar v_n com v_{n-1} na revisão (Task 17) -- gerar uma versão nova
        # não pode apagar a anterior.
        fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 1, PNG_MINIMO)
        conteudo_v2 = PNG_MINIMO + b"\x00extra"
        fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 2, conteudo_v2)

        self.assertIsNotNone(fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, 1))
        with open(fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, 1), "rb") as f:
            self.assertEqual(f.read(), PNG_MINIMO)
        with open(fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, 2), "rb") as f:
            self.assertEqual(f.read(), conteudo_v2)

    def test_caminho_inexistente_devolve_none(self):
        self.assertIsNone(fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, 1))

    def test_versao_invalida_levanta_value_error(self):
        with self.assertRaises(ValueError):
            fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 0, PNG_MINIMO)
        with self.assertRaises(ValueError):
            fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, -1)

    def test_ficha_id_malformado_levanta_value_error(self):
        # caminho_arquivo_da_ficha (fichas_repo) já valida o formato do ficha_id -- confirma que
        # a validação continua acontecendo passando por este módulo.
        with self.assertRaises(ValueError):
            fdz.salvar_desenho(TENANT_TESTE, "../../etc/passwd", 1, PNG_MINIMO)


if __name__ == "__main__":
    unittest.main()
