# -*- coding: utf-8 -*-
"""Testes automatizados completos de Ingestão, Extração e RAG Multi-Formato.

Cobre especificamente:
1. Fonte única de extensões sincronizada com RAG_CONFIG.
2. Validação e sanitização de parâmetros de configuração (chunk_size, chunk_overlap).
3. Extração normalizada de PDF (.pdf).
4. Extração normalizada de DOCX (.docx) com parágrafos, cabeçalhos e tabelas.
5. Extração normalizada de TXT (.txt) com acentuação e encodings variados.
6. Extração normalizada de Markdown (.md) preservando hierarquia de seções.
7. Extração normalizada de CSV (.csv) com delimitadores automáticos e linhas.
8. Extração normalizada de Excel XLSX (.xlsx) com dados tabulares e múltiplas abas.
9. Extração de Excel (.xlsx / .xls) com estrutura não-tabular (fichas técnicas / chave-valor).
10. Extração de Excel XLS (.xls) legado utilizando fixture estática (sem dependência de xlwt).
11. Extração normalizada de PowerPoint PPTX (.pptx) com slides e tabelas.
12. Tratamento de arquivos vazios e rejeição segura.
13. Tratamento de extensões não suportadas com ValueError.
14. Testes exaustivos de Chunking e Overlap (tamanho pequeno, overlap zero, overlap alto,
    overlap >= tamanho, texto sem espaços, palavras longas, parágrafos grandes) garantindo
    que todos os chunks respeitem `len(chunk) <= tamanho_max` sem loops infinitos.
15. Indexação e recuperação semântica no ChromaDB com exibição de metadados e rotulo_unidade.
16. Isolamento estrito entre tenants com múltiplos formatos.
17. Remoção correta de documentos multi-formato.
"""

import os
import io
import csv
import shutil
import unittest
import docx
import pptx
import openpyxl
from fpdf import FPDF

from rag_config import RAG_CONFIG, validar_chunking_config, atualizar_rag_config
from document_extractors import (
    EXTENSOES_SUPORTADAS,
    SUPPORTED_EXTENSIONS,
    obter_extensoes_suportadas,
    extrair_documento,
    obter_extensao_normalizada
)
from rag_manager import (
    extrair_paginas_pdf,
    extrair_texto_pdf,
    dividir_pagina_em_chunks,
    _dividir_texto_longo_recursivo,
    indexar_documento,
    buscar_contexto_relevante,
    listar_documentos_indexados,
    remover_documento
)


class TestDocumentExtractors(unittest.TestCase):
    """Testes unitários para a camada de extração de documentos."""

    def test_01_extensoes_suportadas_sincronizadas(self):
        """Valida que EXTENSOES_SUPORTADAS é derivada diretamente de RAG_CONFIG."""
        esperadas = {"pdf", "docx", "txt", "md", "csv", "xlsx", "xls", "pptx"}
        atuais = set(obter_extensoes_suportadas())
        self.assertTrue(esperadas.issubset(atuais))
        self.assertEqual(EXTENSOES_SUPORTADAS, obter_extensoes_suportadas())
        self.assertEqual(EXTENSOES_SUPORTADAS, SUPPORTED_EXTENSIONS)

    def test_02_validacao_configuracao_chunking(self):
        """Valida sanitização de chunk_size > 0, chunk_overlap >= 0 e chunk_overlap < chunk_size."""
        # Valores normais
        cs, co = validar_chunking_config(500, 100)
        self.assertEqual((cs, co), (500, 100))

        # chunk_size inválido / negativo / zero
        cs_zero, co_zero = validar_chunking_config(0, 50)
        self.assertEqual(cs_zero, 600)
        self.assertEqual(co_zero, 50)

        cs_neg, _ = validar_chunking_config(-100, 50)
        self.assertEqual(cs_neg, 600)

        # chunk_overlap negativo
        _, co_neg = validar_chunking_config(500, -20)
        self.assertEqual(co_neg, 0)

        # chunk_overlap >= chunk_size
        cs_eq, co_eq = validar_chunking_config(200, 200)
        self.assertEqual(cs_eq, 200)
        self.assertEqual(co_eq, 199)

        cs_gt, co_gt = validar_chunking_config(200, 350)
        self.assertEqual(cs_gt, 200)
        self.assertEqual(co_gt, 199)

    def test_03_extracao_pdf(self):
        """Valida extração estruturada de PDF mantendo páginas e metadados."""
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, "Ficha Tecnica Camisa PDF: Gramatura 130 g/m2.", new_x="LMARGIN", new_y="NEXT")
        stream = io.BytesIO()
        pdf.output(stream)
        stream.seek(0)

        unidades = extrair_documento(stream, nome_arquivo="manual.pdf")
        self.assertEqual(len(unidades), 1)
        self.assertEqual(unidades[0]["pagina"], 1)
        self.assertEqual(unidades[0]["metadados"]["tipo_arquivo"], "pdf")
        self.assertIn("Ficha Tecnica Camisa PDF", unidades[0]["texto"])

    def test_04_extracao_docx_com_tabela(self):
        """Valida extração estruturada de DOCX com cabeçalhos, parágrafos e tabelas."""
        doc = docx.Document()
        doc.add_heading("Manual de Confeccao e Modelagem", level=1)
        doc.add_paragraph("Este manual descreve os procedimentos tecnicos de costura.")

        table = doc.add_table(rows=3, cols=3)
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Tamanho"
        hdr_cells[1].text = "Peito"
        hdr_cells[2].text = "Cintura"

        row1 = table.rows[1].cells
        row1[0].text = "P"
        row1[1].text = "90 cm"
        row1[2].text = "80 cm"

        row2 = table.rows[2].cells
        row2[0].text = "M"
        row2[1].text = "100 cm"
        row2[2].text = "90 cm"

        stream = io.BytesIO()
        doc.save(stream)
        stream.seek(0)

        unidades = extrair_documento(stream, nome_arquivo="manual_costura.docx")
        self.assertGreaterEqual(len(unidades), 1)
        texto_unido = " ".join(u["texto"] for u in unidades)
        self.assertIn("Manual de Confeccao", texto_unido)
        self.assertIn("Tamanho | Peito | Cintura", texto_unido)
        self.assertIn("P | 90 cm | 80 cm", texto_unido)
        self.assertIn("M | 100 cm | 90 cm", texto_unido)
        self.assertEqual(unidades[0]["metadados"]["tipo_arquivo"], "docx")

    def test_05_extracao_txt_com_acentos(self):
        """Valida extração de TXT com caracteres acentuados e normalização."""
        conteudo = "Especificação Técnica:\nTecido: 100% Algodão Maquinetado\nGramatura: 140 g/m²\nBotões: Madrepérola."
        stream = io.BytesIO(conteudo.encode("utf-8"))

        unidades = extrair_documento(stream, nome_arquivo="especificacoes.txt")
        self.assertEqual(len(unidades), 1)
        self.assertEqual(unidades[0]["metadados"]["tipo_arquivo"], "txt")
        self.assertIn("100% Algodão Maquinetado", unidades[0]["texto"])
        self.assertIn("140 g/m²", unidades[0]["texto"])

    def test_06_extracao_markdown(self):
        """Valida extração de Markdown preservando estrutura hierárquica."""
        md_text = """# Guia de Estamparia Digital
## Parâmetros DTF
- Resolução mínima: 300 DPI
- Temperatura de prensagem: 160°C
- Tempo: 15 segundos

| Cor | Tinta | Durabilidade |
| Branco | Pigmentada | Alta |
| Preto | Reativa | Média |
"""
        stream = io.BytesIO(md_text.encode("utf-8"))
        unidades = extrair_documento(stream, nome_arquivo="guia_estamparia.md")
        self.assertGreaterEqual(len(unidades), 1)
        texto_unido = " ".join(u["texto"] for u in unidades)
        self.assertIn("Guia de Estamparia Digital", texto_unido)
        self.assertIn("300 DPI", texto_unido)
        self.assertEqual(unidades[0]["metadados"]["tipo_arquivo"], "md")

    def test_07_extracao_csv(self):
        """Valida extração de CSV preservando mapeamento de colunas e linhas."""
        csv_data = "Codigo;Material;Gramatura;Largura\nM518;Algodao;128 g/m2;145 cm\nMD-200;Liocel;170 g/m2;172 cm\n"
        stream = io.BytesIO(csv_data.encode("utf-8"))

        unidades = extrair_documento(stream, nome_arquivo="catalogo_tecidos.csv")
        self.assertEqual(len(unidades), 2)
        self.assertEqual(unidades[0]["metadados"]["tipo_arquivo"], "csv")
        self.assertEqual(unidades[0]["metadados"]["linha"], 2)
        self.assertIn("Codigo: M518", unidades[0]["texto"])
        self.assertIn("Material: Algodao", unidades[0]["texto"])
        self.assertIn("Gramatura: 128 g/m2", unidades[0]["texto"])

        self.assertEqual(unidades[1]["metadados"]["linha"], 3)
        self.assertIn("Codigo: MD-200", unidades[1]["texto"])
        self.assertIn("Material: Liocel", unidades[1]["texto"])

    def test_08_extracao_xlsx_multiplas_abas(self):
        """Valida extração de XLSX com múltiplas abas tabulares preservando cabeçalhos e metadados."""
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "Tecidos"
        ws1.append(["Ref", "Descricao", "Composicao"])
        ws1.append(["T-01", "Denim Premium", "100% Algodao"])
        ws1.append(["T-02", "Linho Puro", "100% Linho"])

        ws2 = wb.create_sheet(title="Aviamentos")
        ws2.append(["Item", "Especificacao", "Tamanho"])
        ws2.append(["Botao", "Madreperola", "18mm"])

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)

        unidades = extrair_documento(stream, nome_arquivo="planejamento.xlsx")
        self.assertEqual(len(unidades), 3)

        # Aba Tecidos
        self.assertEqual(unidades[0]["metadados"]["tipo_arquivo"], "xlsx")
        self.assertEqual(unidades[0]["metadados"]["aba"], "Tecidos")
        self.assertIn("Aba: Tecidos", unidades[0]["texto"])
        self.assertIn("Ref: T-01", unidades[0]["texto"])
        self.assertIn("Descricao: Denim Premium", unidades[0]["texto"])

        # Aba Aviamentos
        self.assertEqual(unidades[2]["metadados"]["aba"], "Aviamentos")
        self.assertIn("Aba: Aviamentos", unidades[2]["texto"])
        self.assertIn("Item: Botao", unidades[2]["texto"])
        self.assertIn("Especificacao: Madreperola", unidades[2]["texto"])

    def test_09_extracao_xlsx_nao_tabular_ficha_tecnica(self):
        """Valida extração inteligente de aba não-tabular no Excel (ficha técnica chave-valor)."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "FichaTecnica"
        ws.append(["FICHA TÉCNICA CF-2026"])
        ws.append(["Produto:", "Camisa Jeans Feminina"])
        ws.append(["Tecido:", "Millie Denim Maskskin"])
        ws.append(["Composição:", "100% Liocel"])
        ws.append(["Gramatura:", "4.5 oz"])
        ws.append(["Lavagem:", "Clara com puídos"])

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)

        unidades = extrair_documento(stream, nome_arquivo="ficha_produto.xlsx")
        self.assertEqual(len(unidades), 1)
        texto = unidades[0]["texto"]
        self.assertIn("Aba: FichaTecnica", texto)
        self.assertIn("Produto: Camisa Jeans Feminina", texto)
        self.assertIn("Tecido: Millie Denim Maskskin", texto)
        self.assertIn("Composição: 100% Liocel", texto)
        self.assertIn("Gramatura: 4.5 oz", texto)
        self.assertEqual(unidades[0]["metadados"]["rotulo_unidade"], "Aba FichaTecnica (Ficha Técnica)")

    def test_10_extracao_xls_legado_estatico(self):
        """Valida extração de XLS legado a partir de fixture estática (sem depender de xlwt)."""
        caminho_fixture = os.path.join("tests", "fixtures", "estoque_legado.xls")
        if not os.path.exists(caminho_fixture):
            self.skipTest(f"Fixture '{caminho_fixture}' não encontrada no repositório.")

        unidades = extrair_documento(caminho_fixture, nome_arquivo="estoque_legado.xls")
        self.assertGreaterEqual(len(unidades), 1)
        self.assertEqual(unidades[0]["metadados"]["tipo_arquivo"], "xls")
        self.assertEqual(unidades[0]["metadados"]["aba"], "Estoque")
        self.assertIn("SKU: CAM-001", unidades[0]["texto"])
        self.assertIn("Nome: Camisa Social", unidades[0]["texto"])

    def test_11_extracao_pptx_slides_e_tabelas(self):
        """Valida extração de PPTX preservando slides, caixas de texto e tabelas sem fatiamento inválido."""
        prs = pptx.Presentation()

        # Slide 1: Título e subtítulo
        slide1 = prs.slides.add_slide(prs.slide_layouts[0])
        slide1.shapes.title.text = "Apresentação Coleção Inverno 2026"
        slide1.placeholders[1].text = "Visão geral das tendências e matérias-primas."

        # Slide 2: Título e tabela
        slide2 = prs.slides.add_slide(prs.slide_layouts[5])
        slide2.shapes.title.text = "Tabela de Cores da Coleção"
        shapes = slide2.shapes
        table_shape = shapes.add_table(rows=2, cols=2, left=100, top=100, width=500, height=200)
        table = table_shape.table
        table.cell(0, 0).text = "Código Pantone"
        table.cell(0, 1).text = "Nome da Cor"
        table.cell(1, 0).text = "19-4052"
        table.cell(1, 1).text = "Classic Blue"

        stream = io.BytesIO()
        prs.save(stream)
        stream.seek(0)

        unidades = extrair_documento(stream, nome_arquivo="colecao.pptx")
        self.assertEqual(len(unidades), 2)
        self.assertEqual(unidades[0]["metadados"]["tipo_arquivo"], "pptx")
        self.assertEqual(unidades[0]["metadados"]["slide"], 1)
        self.assertIn("Coleção Inverno 2026", unidades[0]["texto"])

        self.assertEqual(unidades[1]["metadados"]["slide"], 2)
        self.assertIn("Código Pantone | Nome da Cor", unidades[1]["texto"])
        self.assertIn("19-4052 | Classic Blue", unidades[1]["texto"])

    def test_12_arquivo_vazio(self):
        """Valida que arquivos vazios retornam lista vazia sem causar crash."""
        stream_vazio = io.BytesIO(b"")
        unidades = extrair_documento(stream_vazio, nome_arquivo="vazio.txt")
        self.assertEqual(unidades, [])

    def test_13_extensao_nao_suportada(self):
        """Valida que extensões inválidas levantam ValueError informativo."""
        stream = io.BytesIO(b"dados binarios desconhecidos")
        with self.assertRaises(ValueError) as ctx:
            extrair_documento(stream, nome_arquivo="arquivo.exe")
        self.assertIn("não é suportada", str(ctx.exception))


class TestRAGChunkingAndPipeline(unittest.TestCase):
    """Testes exaustivos de chunking, limites, overlap e integração multi-formato."""

    TENANT_TESTE = "test_multi_format_tenant"
    TENANT_OUTRO = "test_multi_format_outro"

    @classmethod
    def setUpClass(cls):
        for t in [cls.TENANT_TESTE, cls.TENANT_OUTRO]:
            caminho = os.path.join("tenant_data", "chroma", t)
            if os.path.exists(caminho):
                shutil.rmtree(caminho, ignore_errors=True)

    @classmethod
    def tearDownClass(cls):
        for t in [cls.TENANT_TESTE, cls.TENANT_OUTRO]:
            caminho = os.path.join("tenant_data", "chroma", t)
            if os.path.exists(caminho):
                shutil.rmtree(caminho, ignore_errors=True)

    def test_14_chunking_limites_estritos_e_casos_de_borda(self):
        """Valida rigorosamente que todos os chunks respeitam len(chunk) <= tamanho_max em todos os cenários."""
        # 1. Parágrafos longos normais
        texto_longo = "\n\n".join([
            f"Parágrafo {i}: O processo de fiação têxtil demanda controle estrito de umidade na fábrica."
            for i in range(1, 25)
        ])
        tamanho_max = 200
        chunks = _dividir_texto_longo_recursivo(texto_longo, tamanho_max=tamanho_max, sobreposicao=40)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= tamanho_max for c in chunks), f"Chunks excederam limite: {[len(c) for c in chunks]}")

        # 2. Tamanho de chunk muito pequeno (ex: 25 caracteres)
        chunks_pequenos = _dividir_texto_longo_recursivo(texto_longo, tamanho_max=25, sobreposicao=5)
        self.assertTrue(all(len(c) <= 25 for c in chunks_pequenos))

        # 3. Overlap zero
        chunks_sem_overlap = _dividir_texto_longo_recursivo(texto_longo, tamanho_max=150, sobreposicao=0)
        self.assertTrue(all(len(c) <= 150 for c in chunks_sem_overlap))

        # 4. Overlap próximo ao tamanho do chunk (ex: tamanho 100, overlap 95)
        chunks_overlap_alto = _dividir_texto_longo_recursivo(texto_longo, tamanho_max=100, sobreposicao=95)
        self.assertTrue(all(len(c) <= 100 for c in chunks_overlap_alto))

        # 5. Overlap >= tamanho do chunk (deve ser sanitizado internamente sem loop infinito)
        chunks_overlap_maior = _dividir_texto_longo_recursivo(texto_longo, tamanho_max=80, sobreposicao=120)
        self.assertTrue(all(len(c) <= 80 for c in chunks_overlap_maior))

        # 6. Texto contínuo sem espaços (indivisível por palavras)
        texto_sem_espacos = "A" * 600
        chunks_sem_espacos = _dividir_texto_longo_recursivo(texto_sem_espacos, tamanho_max=50, sobreposicao=10)
        self.assertTrue(all(len(c) <= 50 for c in chunks_sem_espacos))
        self.assertGreater(len(chunks_sem_espacos), 10)

        # 7. Palavra extremamente longa no meio do texto
        texto_palavra_gigante = "Início do texto com uma palavra " + ("SUPER" * 40) + " e continuação final."
        chunks_palavra_gigante = _dividir_texto_longo_recursivo(texto_palavra_gigante, tamanho_max=60, sobreposicao=10)
        self.assertTrue(all(len(c) <= 60 for c in chunks_palavra_gigante))

        # 8. Linha única gigantesca (sem quebras de linha)
        linha_gigante = " ".join(["palavra" + str(i) for i in range(200)])
        chunks_linha = _dividir_texto_longo_recursivo(linha_gigante, tamanho_max=120, sobreposicao=20)
        self.assertTrue(all(len(c) <= 120 for c in chunks_linha))

        # 9. dividir_pagina_em_chunks respeitando tamanho_chunk estritamente
        texto_pagina_longo = "DESCRIÇÕES TÉCNICAS: " + ("Conteúdo técnico longo para validar chunking. " * 30)
        chunks_pagina = dividir_pagina_em_chunks(1, texto_pagina_longo, tamanho_chunk=180, sobreposicao=30)
        self.assertTrue(all(len(c["texto"]) <= 180 for c in chunks_pagina))

    def test_15_indexacao_e_busca_multi_formato_e_fontes(self):
        """Indexa múltiplos formatos (.docx, .csv, .xlsx, .pptx) e valida busca e fontes ricas."""
        # 1. DOCX: Guia de Modelagem
        doc = docx.Document()
        doc.add_heading("Especificação do Vestido Floral", level=1)
        doc.add_paragraph("O Vestido Floral Primavera utiliza tecido Cetim de Seda com forro 100% viscose.")
        stream_docx = io.BytesIO()
        doc.save(stream_docx)
        stream_docx.seek(0)
        unidades_docx = extrair_documento(stream_docx, nome_arquivo="vestido_floral.docx")
        qtd_docx = indexar_documento(self.TENANT_TESTE, "vestido_floral.docx", unidades_docx)
        self.assertGreater(qtd_docx, 0)

        # 2. CSV: Catálogo de Zíperes
        csv_data = "Item;Referencia;Material;Resistencia\nZiper Invisivel;ZIP-INV-45;Nylon 3mm;Alta resistencia a tracao\nZiper Metal;ZIP-MET-60;Latao Envelhecido;Extra forte\n"
        unidades_csv = extrair_documento(io.BytesIO(csv_data.encode("utf-8")), nome_arquivo="ziperes.csv")
        qtd_csv = indexar_documento(self.TENANT_TESTE, "ziperes.csv", unidades_csv)
        self.assertGreater(qtd_csv, 0)

        # 3. PPTX: Apresentação de Sustentabilidade
        prs = pptx.Presentation()
        s1 = prs.slides.add_slide(prs.slide_layouts[0])
        s1.shapes.title.text = "Sustentabilidade e Algodão Orgânico BCI"
        s1.placeholders[1].text = "Nosso compromisso prevê 100% de algodão rastreável certificado pela Better Cotton Initiative até 2028."
        stream_pptx = io.BytesIO()
        prs.save(stream_pptx)
        stream_pptx.seek(0)
        unidades_pptx = extrair_documento(stream_pptx, nome_arquivo="sustentabilidade.pptx")
        qtd_pptx = indexar_documento(self.TENANT_TESTE, "sustentabilidade.pptx", unidades_pptx)
        self.assertGreater(qtd_pptx, 0)

        # 4. XLSX: Tabela de Preços e Prazos
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "PrazosProducao"
        ws.append(["Etapa", "TempoMedio", "Responsavel"])
        ws.append(["Corte Automatizado", "2 dias", "Equipe Alfa"])
        ws.append(["Bordado Industrial", "4 dias", "Equipe Beta"])
        stream_xlsx = io.BytesIO()
        wb.save(stream_xlsx)
        stream_xlsx.seek(0)
        unidades_xlsx = extrair_documento(stream_xlsx, nome_arquivo="prazos.xlsx")
        qtd_xlsx = indexar_documento(self.TENANT_TESTE, "prazos.xlsx", unidades_xlsx)
        self.assertGreater(qtd_xlsx, 0)

        # Valida lista de documentos cadastrados
        docs = listar_documentos_indexados(self.TENANT_TESTE)
        self.assertEqual(len(docs), 4)
        self.assertIn("vestido_floral.docx", docs)
        self.assertIn("ziperes.csv", docs)
        self.assertIn("sustentabilidade.pptx", docs)
        self.assertIn("prazos.xlsx", docs)

        # BUSCA 1: Pergunta sobre o DOCX
        res_docx = buscar_contexto_relevante(self.TENANT_TESTE, "Qual tecido é usado no vestido floral primavera?", top_k=3)
        self.assertGreater(len(res_docx), 0)
        self.assertIn("Cetim de Seda", res_docx[0]["texto"])
        self.assertEqual(res_docx[0]["fonte"], "vestido_floral.docx")

        # BUSCA 2: Pergunta sobre o CSV
        res_csv = buscar_contexto_relevante(self.TENANT_TESTE, "Qual é a referência do zíper invisível?", top_k=3)
        self.assertGreater(len(res_csv), 0)
        self.assertIn("ZIP-INV-45", res_csv[0]["texto"])
        self.assertEqual(res_csv[0]["fonte"], "ziperes.csv")
        self.assertIn("Linha", res_csv[0]["rotulo_unidade"])

        # BUSCA 3: Pergunta sobre o PPTX
        res_pptx = buscar_contexto_relevante(self.TENANT_TESTE, "Qual certificado é exigido para o algodão sustentável?", top_k=3)
        self.assertGreater(len(res_pptx), 0)
        self.assertIn("Better Cotton Initiative", res_pptx[0]["texto"])
        self.assertEqual(res_pptx[0]["fonte"], "sustentabilidade.pptx")
        self.assertEqual(res_pptx[0]["rotulo_unidade"], "Slide 1")

        # BUSCA 4: Pergunta sobre o XLSX
        res_xlsx = buscar_contexto_relevante(self.TENANT_TESTE, "Quanto tempo leva a etapa de corte automatizado?", top_k=3)
        self.assertGreater(len(res_xlsx), 0)
        self.assertIn("2 dias", res_xlsx[0]["texto"])
        self.assertEqual(res_xlsx[0]["fonte"], "prazos.xlsx")
        self.assertIn("Aba PrazosProducao", res_xlsx[0]["rotulo_unidade"])

    def test_16_isolamento_multi_tenant(self):
        """Valida que documentos indexados em um tenant não vazam para outro tenant."""
        csv_secreto = "Chave;Valor\nConfidencial;CODIGO-ULTRA-SECRETO-999\n"
        unidades_sec = extrair_documento(io.BytesIO(csv_secreto.encode("utf-8")), nome_arquivo="segredos.csv")
        indexar_documento(self.TENANT_OUTRO, "segredos.csv", unidades_sec)

        # Busca no TENANT_TESTE
        res_teste = buscar_contexto_relevante(self.TENANT_TESTE, "CODIGO-ULTRA-SECRETO-999", top_k=5)
        for r in res_teste:
            self.assertNotIn("CODIGO-ULTRA-SECRETO-999", r["texto"])

        # Busca no TENANT_OUTRO
        res_outro = buscar_contexto_relevante(self.TENANT_OUTRO, "CODIGO-ULTRA-SECRETO-999", top_k=5)
        self.assertGreater(len(res_outro), 0)
        self.assertIn("CODIGO-ULTRA-SECRETO-999", res_outro[0]["texto"])

    def test_17_remocao_documento_multi_formato(self):
        """Valida que a remoção limpa o documento da coleção corretamente."""
        self.assertTrue(remover_documento(self.TENANT_TESTE, "ziperes.csv"))
        docs_restantes = listar_documentos_indexados(self.TENANT_TESTE)
        self.assertNotIn("ziperes.csv", docs_restantes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
