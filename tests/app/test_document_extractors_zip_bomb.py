# -*- coding: utf-8 -*-
"""Integração: `extrair_documento_com_dados_tabulares` rejeita zip bomb antes de chamar o parser
específico (Fase 15, V7).

Um `.docx`/`.xlsx`/`.pptx` malicioso não precisa ser grande: uma única entrada ZIP repetitiva
comprime para poucos KB (bem dentro do limite de 20MB de upload) e ainda assim descompactaria para
centenas de MB. Este teste usa um caso desse tipo -- não um mock -- para provar que a extração
recusa ANTES de `docx.Document` tentar descompactar tudo na memória.
"""

import io
import unittest
import zipfile

from document_extractors import extrair_documento_com_dados_tabulares


def _docx_bomba(bytes_descompactados: int) -> bytes:
    """Um ZIP de poucos KB que descompactaria para `bytes_descompactados` -- não precisa ser um
    .docx estruturalmente válido, porque a checagem de zip bomb roda antes do `docx.Document`
    sequer tentar interpretar o conteúdo."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("word/document.xml", b"A" * bytes_descompactados)
    return buffer.getvalue()


class TestExtracaoRecusaZipBomb(unittest.TestCase):

    def test_docx_com_taxa_de_compressao_absurda_e_recusado(self):
        conteudo = _docx_bomba(310 * 1024 * 1024)  # descompacta > 300MB, ocupa ~poucos KB no ZIP
        self.assertLess(len(conteudo), 1 * 1024 * 1024)  # bem dentro do limite normal de upload

        with self.assertRaises(ValueError) as ctx:
            extrair_documento_com_dados_tabulares(conteudo, nome_arquivo="relatorio.docx")

        # `verificar_zip_bomb` levanta ValueError direto (não é o `except Exception` genérico da
        # Fase 15, V5, então a mensagem não é reescrita) -- confirma que é a rejeição de zip bomb,
        # não outro tipo de falha de parsing.
        self.assertIn("descompactaria", str(ctx.exception))

    def test_docx_normal_dentro_do_limite_continua_funcionando(self):
        import docx as python_docx
        buffer = io.BytesIO()
        documento = python_docx.Document()
        documento.add_paragraph("Texto de teste, nada suspeito.")
        documento.save(buffer)

        unidades, _ = extrair_documento_com_dados_tabulares(buffer.getvalue(), nome_arquivo="normal.docx")
        self.assertTrue(any("Texto de teste" in u["texto"] for u in unidades))


if __name__ == "__main__":
    unittest.main()
