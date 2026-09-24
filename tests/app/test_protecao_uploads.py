# -*- coding: utf-8 -*-
"""Proteção contra zip bomb em uploads .docx/.xlsx/.pptx (Fase 15, V7).

.docx/.xlsx/.pptx são arquivos ZIP por baixo -- `docx.Document`/`openpyxl.load_workbook`/
`pptx.Presentation` descompactam sem limite próprio. Não é preciso um zip bomb real (GBs) para
testar: um limite artificialmente baixo já prova que `verificar_zip_bomb` soma corretamente
`file_size` (o tamanho DESCOMPACTADO, não o tamanho no disco) e levanta a exceção certa.
"""

import io
import unittest
import zipfile

from protecao_uploads import verificar_zip_bomb


def _construir_zip(conteudos: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, dados in conteudos.items():
            zf.writestr(nome, dados)
    return buffer.getvalue()


class TestVerificarZipBomb(unittest.TestCase):

    def test_zip_pequeno_dentro_do_limite_nao_levanta_erro(self):
        conteudo = _construir_zip({"documento.xml": b"conteudo pequeno"})
        verificar_zip_bomb(conteudo, limite_bytes=10_000)  # não deve levantar

    def test_zip_que_descompactaria_acima_do_limite_levanta_value_error(self):
        # Um único arquivo repetitivo comprime muito bem -- poucos KB no ZIP, mas
        # `file_size` (descompactado) fica bem acima de um limite artificialmente baixo.
        conteudo = _construir_zip({"grande.xml": b"A" * 50_000})
        with self.assertRaises(ValueError):
            verificar_zip_bomb(conteudo, limite_bytes=1_000)

    def test_soma_o_tamanho_descompactado_de_todas_as_entradas(self):
        # Nenhuma entrada sozinha excede o limite, mas a SOMA excede.
        conteudo = _construir_zip({
            "parte1.xml": b"X" * 600,
            "parte2.xml": b"Y" * 600,
        })
        with self.assertRaises(ValueError):
            verificar_zip_bomb(conteudo, limite_bytes=1_000)

    def test_arquivo_que_nao_e_zip_nao_levanta_erro(self):
        # Não é responsabilidade desta função rejeitar um arquivo corrompido -- isso é do parser
        # específico (docx/openpyxl/pptx), que vai dar sua própria mensagem de erro.
        verificar_zip_bomb(b"isto claramente nao e um zip", limite_bytes=10)


if __name__ == "__main__":
    unittest.main()
