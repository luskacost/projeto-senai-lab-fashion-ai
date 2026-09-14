# -*- coding: utf-8 -*-
"""Testes da conversão para PDF (Fase 11, Task 13).

Os testes que de fato convertem exigem o LibreOffice instalado e se pulam sozinhos quando ele não
existe (`skipUnless`). Isso é proposital: o CI do projeto roda numa máquina enxuta sem
LibreOffice, e o roadmap não prevê instalá-lo lá -- fazer o CI falhar por uma dependência de
sistema ausente treinaria todo mundo a ignorar CI vermelho.

O que NÃO depende do LibreOffice (localização do executável, tratamento de erro, contrato das
exceções) é testado sempre.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import fichas_docx as fd
import fichas_modelo as fm
import fichas_pdf as fp

TEM_LIBREOFFICE = fp.libreoffice_disponivel()
MOTIVO_PULO = "LibreOffice não instalado neste ambiente"


class TestLocalizacaoDoExecutavel(unittest.TestCase):

    def test_variavel_de_ambiente_tem_prioridade(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as arquivo:
            caminho_falso = arquivo.name
        try:
            with patch.dict(os.environ, {"LIBREOFFICE_PATH": caminho_falso}):
                self.assertEqual(fp.encontrar_libreoffice(), caminho_falso)
        finally:
            os.remove(caminho_falso)

    def test_variavel_apontando_para_caminho_inexistente_devolve_none(self):
        # Melhor devolver None (e cair no 501 com mensagem clara) do que tentar executar um
        # caminho que não existe e falhar com um erro de sistema opaco.
        with patch.dict(os.environ, {"LIBREOFFICE_PATH": os.path.join("caminho", "que", "nao", "existe")}):
            self.assertIsNone(fp.encontrar_libreoffice())

    def test_disponivel_reflete_a_busca(self):
        with patch.object(fp, "encontrar_libreoffice", return_value=None):
            self.assertFalse(fp.libreoffice_disponivel())
        with patch.object(fp, "encontrar_libreoffice", return_value="/usr/bin/soffice"):
            self.assertTrue(fp.libreoffice_disponivel())


class TestTratamentoDeErro(unittest.TestCase):

    def setUp(self):
        self.diretorio = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.diretorio, ignore_errors=True)

    def test_sem_libreoffice_levanta_erro_especifico(self):
        with patch.object(fp, "encontrar_libreoffice", return_value=None):
            with self.assertRaises(fp.LibreOfficeIndisponivelError) as contexto:
                fp.converter_para_pdf("qualquer.docx", os.path.join(self.diretorio, "saida.pdf"))
        # A mensagem precisa dizer o que fazer, não só que falhou.
        self.assertIn("LIBREOFFICE_PATH", str(contexto.exception))

    def test_origem_inexistente_levanta_erro(self):
        with patch.object(fp, "encontrar_libreoffice", return_value="/usr/bin/soffice"):
            with self.assertRaises(fp.ConversaoPdfError):
                fp.converter_para_pdf(
                    os.path.join(self.diretorio, "nao_existe.docx"),
                    os.path.join(self.diretorio, "saida.pdf"),
                )


@unittest.skipUnless(TEM_LIBREOFFICE, MOTIVO_PULO)
class TestConversaoReal(unittest.TestCase):
    """Conversão de verdade, com o LibreOffice instalado."""

    @classmethod
    def setUpClass(cls):
        cls.diretorio = tempfile.mkdtemp()
        cls.docx = os.path.join(cls.diretorio, "ficha.docx")
        fd.renderizar_para_arquivo(_ficha_exemplo(), cls.docx)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.diretorio, ignore_errors=True)

    def test_gera_um_pdf_valido(self):
        destino = os.path.join(self.diretorio, "saida.pdf")
        fp.converter_para_pdf(self.docx, destino)

        self.assertTrue(os.path.exists(destino))
        with open(destino, "rb") as f:
            self.assertTrue(f.read(5).startswith(b"%PDF-"), "o arquivo não tem assinatura de PDF")

    def test_pdf_preserva_o_texto_da_ficha(self):
        # O PDF precisa conter os dados, não ser uma casca vazia -- é o que garante que o
        # LibreOffice de fato renderizou o conteúdo, e não só abriu e salvou um documento em branco.
        from pypdf import PdfReader

        destino = os.path.join(self.diretorio, "com_texto.pdf")
        fp.converter_para_pdf(self.docx, destino)

        texto = "\n".join(pagina.extract_text() or "" for pagina in PdfReader(destino).pages)
        for esperado in ("CM-001", "Camisa Social Branca", "FICHA"):
            with self.subTest(valor=esperado):
                self.assertIn(esperado, texto)

    def test_conta_paginas(self):
        destino = os.path.join(self.diretorio, "paginas.pdf")
        fp.converter_para_pdf(self.docx, destino)
        self.assertGreaterEqual(fp.contar_paginas(destino), 1)

    def test_conversoes_seguidas_nao_disputam_perfil(self):
        # Cada invocação usa um perfil próprio do LibreOffice; sem isso, conversões concorrentes
        # disputam o mesmo perfil e a segunda trava ou falha em silêncio.
        for indice in range(3):
            destino = os.path.join(self.diretorio, f"seguida_{indice}.pdf")
            fp.converter_para_pdf(self.docx, destino)
            self.assertTrue(os.path.exists(destino))


def _ficha_exemplo() -> dict:
    def campo(valor):
        return {"valor": valor, "origem": fm.ORIGEM_FORNECIDO, "trecho": ""}

    ficha = fm.ficha_vazia()
    ficha["id"] = "44444444-4444-4444-4444-444444444444"
    ficha["dados"]["ficha"]["ref"] = campo("CM-001")
    ficha["dados"]["ficha"]["nome"] = campo("Camisa Social Branca")
    ficha["dados"]["ficha"]["descricao"] = campo("Camisa social manga longa")
    return ficha


if __name__ == "__main__":
    unittest.main()
