# -*- coding: utf-8 -*-
"""Testes do logo da empresa (Fase 11, Task 11).

Usa um tenant fictício próprio e limpa tenant_data/branding/{tenant}* no tearDown, para não
tocar no logo real do SENAI nem deixar debris.
"""

import glob
import io
import os
import shutil
import tempfile
import unittest

from PIL import Image
from docx import Document
from docxtpl import DocxTemplate

import fichas_docx as fd
import fichas_logo as fl
import fichas_modelo as fm

TENANT_TESTE = "teste_task11_logo"


def _png_bytes(largura: int, altura: int, cor=(200, 30, 30, 255)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (largura, altura), cor).save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes(largura: int, altura: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (largura, altura), (10, 60, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


class TestLogoBase(unittest.TestCase):
    def setUp(self):
        self._limpar()

    def tearDown(self):
        self._limpar()

    def _limpar(self):
        for caminho in glob.glob(os.path.join(fl.DIRETORIO_BRANDING, f"{TENANT_TESTE}_logo.*")):
            os.remove(caminho)


class TestValidacaoDoUpload(TestLogoBase):

    def test_png_valido_e_aceito(self):
        metadados = fl.salvar_logo(TENANT_TESTE, _png_bytes(400, 120), "logo.png")
        self.assertEqual(metadados["largura_px"], 400)
        self.assertEqual(metadados["altura_px"], 120)
        self.assertEqual(metadados["formato_origem"], "PNG")

    def test_jpeg_valido_e_aceito_e_convertido(self):
        fl.salvar_logo(TENANT_TESTE, _jpeg_bytes(300, 300), "logo.jpg")
        # Independente do formato de entrada, o que fica em disco é sempre PNG -- o resto do
        # código não precisa adivinhar extensão.
        with Image.open(fl.caminho_logo(TENANT_TESTE)) as imagem:
            self.assertEqual(imagem.format, "PNG")

    def test_transparencia_e_preservada(self):
        # Requisito explícito do usuário: logo com fundo transparente não pode virar retângulo
        # branco no documento.
        transparente = _png_bytes(100, 100, cor=(255, 0, 0, 0))
        fl.salvar_logo(TENANT_TESTE, transparente, "logo.png")

        with Image.open(fl.caminho_logo(TENANT_TESTE)) as imagem:
            self.assertEqual(imagem.mode, "RGBA")
            self.assertEqual(imagem.getpixel((0, 0))[3], 0, "o canal alfa se perdeu")

    def test_arquivo_que_nao_e_imagem_e_recusado(self):
        with self.assertRaises(fl.LogoInvalidoError):
            fl.salvar_logo(TENANT_TESTE, b"isso aqui nao e uma imagem", "logo.png")

    def test_svg_e_recusado_com_mensagem_clara(self):
        # O Word não embute SVG por esse caminho. Recusar no upload é melhor que falhar depois,
        # na geração do documento, quando o usuário já não associa o erro ao arquivo enviado.
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
        with self.assertRaises(fl.LogoInvalidoError) as contexto:
            fl.salvar_logo(TENANT_TESTE, svg, "logo.svg")
        self.assertIn("SVG", str(contexto.exception))

    def test_arquivo_vazio_e_recusado(self):
        with self.assertRaises(fl.LogoInvalidoError):
            fl.salvar_logo(TENANT_TESTE, b"", "logo.png")

    def test_arquivo_grande_demais_e_recusado(self):
        gigante = b"\x89PNG\r\n\x1a\n" + b"0" * (fl.LIMITE_LOGO_BYTES + 1)
        with self.assertRaises(fl.LogoInvalidoError) as contexto:
            fl.salvar_logo(TENANT_TESTE, gigante, "logo.png")
        self.assertIn("MB", str(contexto.exception))


class TestCicloDeVida(TestLogoBase):

    def test_sem_logo_cadastrado(self):
        self.assertIsNone(fl.caminho_logo(TENANT_TESTE))
        self.assertIsNone(fl.metadados_logo(TENANT_TESTE))

    def test_salvar_e_recuperar(self):
        fl.salvar_logo(TENANT_TESTE, _png_bytes(200, 80), "meu_logo.png")
        self.assertIsNotNone(fl.caminho_logo(TENANT_TESTE))
        self.assertEqual(fl.metadados_logo(TENANT_TESTE)["nome_original"], "meu_logo.png")

    def test_substituir_logo(self):
        fl.salvar_logo(TENANT_TESTE, _png_bytes(200, 80), "antigo.png")
        fl.salvar_logo(TENANT_TESTE, _png_bytes(500, 100), "novo.png")

        metadados = fl.metadados_logo(TENANT_TESTE)
        self.assertEqual(metadados["nome_original"], "novo.png")
        self.assertEqual(metadados["largura_px"], 500)

    def test_remover(self):
        fl.salvar_logo(TENANT_TESTE, _png_bytes(200, 80), "logo.png")
        self.assertTrue(fl.remover_logo(TENANT_TESTE))
        self.assertIsNone(fl.caminho_logo(TENANT_TESTE))

    def test_remover_sem_logo_devolve_false(self):
        self.assertFalse(fl.remover_logo(TENANT_TESTE))


class TestDimensionamentoProporcional(unittest.TestCase):
    """Requisito do usuário: preservar proporção, nunca esticar, nunca ultrapassar a área."""

    def test_logo_largo_limitado_pela_largura(self):
        largura, altura = fl.calcular_dimensoes_cm(400, 100)
        self.assertAlmostEqual(largura, fl.LARGURA_MAX_CM, places=4)
        self.assertLessEqual(altura, fl.ALTURA_MAX_CM)

    def test_logo_alto_limitado_pela_altura(self):
        # Escalar só pela largura deixaria este logo com 3,6cm de altura e estouraria o cabeçalho.
        largura, altura = fl.calcular_dimensoes_cm(100, 400)
        self.assertAlmostEqual(altura, fl.ALTURA_MAX_CM, places=4)
        self.assertLessEqual(largura, fl.LARGURA_MAX_CM)

    def test_proporcao_e_sempre_preservada(self):
        for largura_px, altura_px in [(400, 100), (100, 400), (250, 250), (1920, 1080), (37, 913)]:
            with self.subTest(dimensoes=(largura_px, altura_px)):
                largura_cm, altura_cm = fl.calcular_dimensoes_cm(largura_px, altura_px)
                self.assertAlmostEqual(
                    largura_cm / altura_cm, largura_px / altura_px, places=4,
                    msg="a imagem foi esticada -- a proporção original mudou",
                )

    def test_nunca_ultrapassa_a_area_reservada(self):
        for largura_px, altura_px in [(4000, 20), (20, 4000), (1, 1), (5000, 5000)]:
            with self.subTest(dimensoes=(largura_px, altura_px)):
                largura_cm, altura_cm = fl.calcular_dimensoes_cm(largura_px, altura_px)
                self.assertLessEqual(round(largura_cm, 6), fl.LARGURA_MAX_CM)
                self.assertLessEqual(round(altura_cm, 6), fl.ALTURA_MAX_CM)

    def test_dimensoes_invalidas_nao_quebram(self):
        largura, altura = fl.calcular_dimensoes_cm(0, 0)
        self.assertGreater(largura, 0)
        self.assertGreater(altura, 0)


class TestLogoNoDocumento(TestLogoBase):
    """O logo precisa chegar de fato ao .docx gerado."""

    def setUp(self):
        super().setUp()
        self.diretorio = tempfile.mkdtemp()

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.diretorio, ignore_errors=True)

    def _renderizar(self) -> str:
        caminho = os.path.join(self.diretorio, "ficha.docx")
        return fd.renderizar_para_arquivo(fm.ficha_vazia(), caminho, tenant_id=TENANT_TESTE)

    def test_sem_logo_a_area_fica_limpa(self):
        # "Se não houver logo cadastrado, a área deve permanecer limpa" -- e o documento tem que
        # ser gerado normalmente, sem erro.
        doc = Document(self._renderizar())
        self.assertEqual(len(doc.inline_shapes), 0)

    def test_com_logo_a_imagem_entra_no_documento(self):
        fl.salvar_logo(TENANT_TESTE, _png_bytes(400, 120), "logo.png")
        doc = Document(self._renderizar())
        self.assertEqual(len(doc.inline_shapes), 1, "o logo não foi embutido no .docx")

    def test_imagem_entra_com_as_dimensoes_calculadas(self):
        fl.salvar_logo(TENANT_TESTE, _png_bytes(400, 100), "logo.png")
        doc = Document(self._renderizar())

        forma = doc.inline_shapes[0]
        largura_esperada, altura_esperada = fl.calcular_dimensoes_cm(400, 100)
        self.assertAlmostEqual(forma.width.cm, largura_esperada, places=1)
        self.assertAlmostEqual(forma.height.cm, altura_esperada, places=1)

    def test_logo_corrompido_nao_impede_a_geracao(self):
        # Um logo ilegível não pode derrubar a geração da ficha inteira -- o documento sai sem ele.
        fl.salvar_logo(TENANT_TESTE, _png_bytes(100, 100), "logo.png")
        with open(fl.caminho_logo(TENANT_TESTE), "wb") as f:
            f.write(b"arquivo corrompido")

        doc = Document(self._renderizar())
        self.assertEqual(len(doc.inline_shapes), 0)

    def test_logo_para_documento_sem_cadastro_devolve_none(self):
        modelo = DocxTemplate(fd.CAMINHO_TEMPLATE)
        self.assertIsNone(fl.logo_para_documento(modelo, TENANT_TESTE))


if __name__ == "__main__":
    unittest.main()
