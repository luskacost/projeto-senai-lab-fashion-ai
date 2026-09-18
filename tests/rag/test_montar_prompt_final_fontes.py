# -*- coding: utf-8 -*-
"""`montar_prompt_final` devolve fontes na mesma ordem/tamanho dos chunks (Fase 13, Task 17).

Antes: devolvia um `Set[str]` deduplicado. O chamador (tanto o modo "Base de Conhecimento" em
api/main.py quanto a ferramenta buscar_documentos_internos em agente_ferramentas.py) usa essa
lista lado a lado com a lista de chunks originais, pareando por ÍNDICE na UI/no agente -- um
conjunto de tamanho e ordem diferentes desalinhava esse pareamento a partir do primeiro chunk
cuja fonte já tivesse aparecido antes.
"""

import unittest

from rag_manager import montar_prompt_final


class TestFontesConsultadasParalelasAosChunks(unittest.TestCase):

    def test_uma_fonte_por_chunk_mesma_ordem(self):
        chunks = [
            {"fonte": "manual.pdf", "texto": "a", "pagina": 3},
            {"fonte": "catalogo.csv", "texto": "b", "rotulo_unidade": "Linha 5"},
            {"fonte": "manual.pdf", "texto": "c", "pagina": 7},
        ]
        _, fontes = montar_prompt_final(chunks, "pergunta")
        self.assertEqual(
            fontes, ["manual.pdf (Página 3)", "catalogo.csv (Linha 5)", "manual.pdf (Página 7)"]
        )

    def test_duas_fontes_da_mesma_origem_nao_colapsam(self):
        # O ponto central do defeito: duas páginas do MESMO documento não podem virar 1 fonte só,
        # ou a lista de fontes fica mais curta que a de chunks.
        chunks = [
            {"fonte": "manual.pdf", "texto": "a", "pagina": 3},
            {"fonte": "manual.pdf", "texto": "b", "pagina": 3},
        ]
        _, fontes = montar_prompt_final(chunks, "pergunta")
        self.assertEqual(len(fontes), len(chunks))

    def test_fontes_e_chunks_sempre_do_mesmo_tamanho(self):
        chunks = [{"fonte": f"doc{i}.pdf", "texto": str(i), "pagina": i} for i in range(5)]
        _, fontes = montar_prompt_final(chunks, "pergunta")
        self.assertEqual(len(fontes), len(chunks))

    def test_lista_vazia(self):
        _, fontes = montar_prompt_final([], "pergunta")
        self.assertEqual(fontes, [])


if __name__ == "__main__":
    unittest.main()
