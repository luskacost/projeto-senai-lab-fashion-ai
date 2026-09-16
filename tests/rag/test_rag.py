# -*- coding: utf-8 -*-
"""Testes automatizados completos para validação do pipeline RAG avançado.

Cobre especificamente:
1. Extração estruturada por página de PDF.
2. Preservação de blocos lógicos de especificações sem quebra.
3. Teste 1: 'Qual é a gramatura do tecido M518?' -> M518 e 128 g/m²
4. Teste 2: 'Qual tecido é especificado para a camisa jeans feminina?' -> Millie Denim Maskskin
5. Teste 3: 'Qual é a composição da camisa jeans?' -> 100% liocel (sem misturar com M518 algodão)
6. Teste 4: 'Qual é a largura do tecido da camisa jeans?' -> 172 cm
7. Teste 5: 'Qual é a composição do fio utilizado na etiqueta lateral?' -> 50% poliéster e 50% algodão
8. Teste 6: 'Qual é a diferença entre M518 e Millie Denim Maskskin?' -> evidências de ambas as entidades
9. Teste 7: 'Qual é o preço de produção da camisa?' -> sem evidências inventadas
10. Teste 8: 'Qual empresa fornece o tecido M518?' -> sem fornecedor inventado
11. Isolamento multi-tenant estrito (tenant_a vs tenant_b).
12. Remoção e listagem de documentos.
"""

import os
import shutil
import unittest
import tempfile
from fpdf import FPDF
from rag_manager import (
    extrair_paginas_pdf,
    extrair_texto_pdf,
    dividir_pagina_em_chunks,
    indexar_documento,
    buscar_contexto_relevante,
    listar_documentos_indexados,
    remover_documento,
    RAG_SIMILARITY_THRESHOLD,
)
from .fixtures_prioridades_rag import _ativar_config_de_teste, _restaurar_config_de_teste

# Documento de teste realista simulando um manual técnico com múltiplas páginas e variantes
DOC_TECNICO_PAGINA_1 = """SENAI LABFASHION - FICHA TÉCNICA DE PRODUTO
PRODUTO: Camisa Feminina Manga Longa
REFERÊNCIA GERAL: CF-2026

1. ESPECIFICAÇÕES DO MODELO BASE (VARIANTE TRADICIONAL):
Tecido: M518
Composição: 100% ALGODÃO
Gramatura: 128 g/m²
Largura: 145 cm
Acabamento: Toque suave, pré-encolhido."""

DOC_TECNICO_PAGINA_2 = """2. ESPECIFICAÇÕES DA VARIANTE JEANS:
PRODUTO: Camisa Feminina Manga Longa
VARIANTE: Jeans / Denim
Tecido: Millie Denim Maskskin
Composição: 100% LIOCEL
Gramatura: 4,5 oz
Largura: 172 cm
Lavagem: Clara com puídos leves."""

DOC_TECNICO_PAGINA_3 = """3. ESPECIFICAÇÕES DE AVIAMENTOS E ETIQUETAS:
Botões: Madrepérola 18mm (6 unidades frontais + 2 punhos).
Etiqueta lateral de composição:
Fio: 50% poliéster e 50% algodão
Linha de costura principal: 100% poliéster 120."""


def _criar_pdf_multi_pagina(caminho: str):
    """Gera um arquivo PDF com 3 páginas técnicas formatadas."""
    pdf = FPDF()
    paginas = [DOC_TECNICO_PAGINA_1, DOC_TECNICO_PAGINA_2, DOC_TECNICO_PAGINA_3]
    for idx, conteudo in enumerate(paginas, 1):
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        for linha in conteudo.split("\n"):
            pdf.cell(0, 7, linha.encode("latin-1", "replace").decode("latin-1"), new_x="LMARGIN", new_y="NEXT")
    pdf.output(caminho)


class TestRAGAvancado(unittest.TestCase):
    TENANT_TESTE = "teste_rag_tecnico"
    TENANT_OUTRO = "teste_rag_outro"

    @classmethod
    def setUpClass(cls):
        # Limpa dados de testes prévios
        for t in [cls.TENANT_TESTE, cls.TENANT_OUTRO]:
            caminho = os.path.join("tenant_data", "chroma", t)
            if os.path.exists(caminho):
                shutil.rmtree(caminho, ignore_errors=True)

        # Fase 13, Task 3: a classificação de metadado (variante Jeans/M518) e o bônus/penalidade
        # de alinhamento no reranker viraram opt-in por tenant (default vazio) -- este fixture
        # ativa a config equivalente à que antes era hardcoded, para os testes de desambiguação
        # abaixo continuarem provando que o MECANISMO funciona quando configurado.
        _ativar_config_de_teste()

        # Cria PDF multi-páginas de teste
        cls.pdf_teste_path = "temp_ficha_tecnica_teste.pdf"
        _criar_pdf_multi_pagina(cls.pdf_teste_path)

        # Indexa o PDF no tenant de teste
        paginas = extrair_paginas_pdf(cls.pdf_teste_path)
        indexar_documento(cls.TENANT_TESTE, "ficha_tecnica_camisa.pdf", paginas)

    @classmethod
    def tearDownClass(cls):
        for t in [cls.TENANT_TESTE, cls.TENANT_OUTRO]:
            caminho = os.path.join("tenant_data", "chroma", t)
            if os.path.exists(caminho):
                shutil.rmtree(caminho, ignore_errors=True)
        if os.path.exists(cls.pdf_teste_path):
            try:
                os.remove(cls.pdf_teste_path)
            except Exception:
                pass
        _restaurar_config_de_teste()

    def test_01_extracao_paginas(self):
        """Valida que o PDF é extraído mantendo 3 páginas individuais com metadados corretos."""
        paginas = extrair_paginas_pdf(self.pdf_teste_path)
        self.assertEqual(len(paginas), 3)
        self.assertEqual(paginas[0]["pagina"], 1)
        self.assertIn("M518", paginas[0]["texto"])
        self.assertEqual(paginas[1]["pagina"], 2)
        self.assertIn("Millie Denim Maskskin", paginas[1]["texto"])
        self.assertEqual(paginas[2]["pagina"], 3)
        self.assertIn("Etiqueta lateral", paginas[2]["texto"])

    def test_02_consulta_gramatura_m518(self):
        """Consulta 1: 'Qual é a gramatura do tecido M518?' -> Deve recuperar M518 e 128 g/m²."""
        query = "Qual é a gramatura do tecido M518?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        self.assertGreater(len(resultados), 0)
        top = resultados[0]
        self.assertIn("M518", top["texto"])
        self.assertIn("128 g/m²", top["texto"])
        self.assertEqual(top["pagina"], 1)

    def test_03_consulta_tecido_camisa_jeans(self):
        """Consulta 2: 'Qual tecido é especificado para a camisa jeans feminina?' -> Millie Denim Maskskin."""
        query = "Qual tecido é especificado para a camisa jeans feminina?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        self.assertGreater(len(resultados), 0)
        top = resultados[0]
        self.assertIn("Millie Denim Maskskin", top["texto"])
        self.assertEqual(top["pagina"], 2)

    def test_04_consulta_composicao_camisa_jeans(self):
        """Consulta 3: 'Qual é a composição da camisa jeans?' -> 100% liocel (NÃO algodão)."""
        query = "Qual é a composição da camisa jeans?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        self.assertGreater(len(resultados), 0)
        top = resultados[0]
        self.assertIn("100% LIOCEL", top["texto"].upper())
        self.assertNotIn("100% ALGODÃO", top["texto"].upper())
        self.assertEqual(top["pagina"], 2)

    def test_05_consulta_largura_tecido_jeans(self):
        """Consulta 4: 'Qual é a largura do tecido da camisa jeans?' -> 172 cm."""
        query = "Qual é a largura do tecido da camisa jeans?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        self.assertGreater(len(resultados), 0)
        top = resultados[0]
        self.assertIn("172 cm", top["texto"])
        self.assertEqual(top["pagina"], 2)

    def test_06_consulta_fio_etiqueta_lateral(self):
        """Consulta 5: 'Qual é a composição do fio utilizado na etiqueta lateral?' -> 50% poliéster e 50% algodão."""
        query = "Qual é a composição do fio utilizado na etiqueta lateral?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        self.assertGreater(len(resultados), 0)
        top = resultados[0]
        self.assertIn("50% poliéster", top["texto"].lower())
        self.assertIn("50% algodão", top["texto"].lower())
        self.assertEqual(top["pagina"], 3)

    def test_07_consulta_comparativa_m518_vs_millie(self):
        """Consulta 6: 'Qual é a diferença entre M518 e Millie Denim Maskskin?' -> Deve recuperar ambos."""
        query = "Qual é a diferença entre M518 e Millie Denim Maskskin?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        self.assertGreaterEqual(len(resultados), 2)
        textos_unidos = " ".join([r["texto"] for r in resultados])
        self.assertIn("M518", textos_unidos)
        self.assertIn("Millie Denim Maskskin", textos_unidos)
        # Verifica que ambas as páginas (1 e 2) estão presentes nos resultados
        paginas_recuperadas = set(r["pagina"] for r in resultados)
        self.assertIn(1, paginas_recuperadas)
        self.assertIn(2, paginas_recuperadas)

    def test_08_consulta_sem_evidencia_preco(self):
        """Consulta 7: 'Qual é o preço de produção da camisa?' -> Não deve conter informação de preço."""
        query = "Qual é o preço de produção da camisa?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        for r in resultados:
            self.assertNotIn("R$", r["texto"])
            self.assertNotIn("preço", r["texto"].lower())

    def test_09_consulta_sem_evidencia_fornecedor(self):
        """Consulta 8: 'Qual empresa fornece o tecido M518?' -> Não deve conter fornecedor."""
        query = "Qual empresa fornece o tecido M518?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        for r in resultados:
            self.assertNotIn("fornecedor:", r["texto"].lower())

    def test_10_isolamento_multi_tenant(self):
        """Valida que o tenant_outro não acessa dados do tenant_teste."""
        doc_outro = "outro_documento.pdf"
        texto_outro = "Dados confidenciais exclusivos do Tenant Outro: chave secreta TOP-SECRET-999."
        indexar_documento(self.TENANT_OUTRO, doc_outro, texto_outro)

        # Busca no TENANT_TESTE não deve retornar nada do TENANT_OUTRO
        res_teste = buscar_contexto_relevante(self.TENANT_TESTE, "chave secreta TOP-SECRET-999", top_k=5)
        for r in res_teste:
            self.assertNotIn("TOP-SECRET-999", r["texto"])

        # Busca no TENANT_OUTRO deve retornar
        res_outro = buscar_contexto_relevante(self.TENANT_OUTRO, "chave secreta TOP-SECRET-999", top_k=5)
        self.assertGreater(len(res_outro), 0)
        self.assertIn("TOP-SECRET-999", res_outro[0]["texto"])

    def test_11_remocao_documento(self):
        """Valida que a remoção limpa o documento da coleção."""
        docs_antes = listar_documentos_indexados(self.TENANT_TESTE)
        self.assertIn("ficha_tecnica_camisa.pdf", docs_antes)

        sucesso = remover_documento(self.TENANT_TESTE, "ficha_tecnica_camisa.pdf")
        self.assertTrue(sucesso)

        docs_depois = listar_documentos_indexados(self.TENANT_TESTE)
        self.assertNotIn("ficha_tecnica_camisa.pdf", docs_depois)


if __name__ == "__main__":
    unittest.main(verbosity=2)
