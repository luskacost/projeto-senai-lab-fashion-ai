# -*- coding: utf-8 -*-
"""Cenários de ponta a ponta do gerador de fichas técnicas (Fase 11, Task 19).

Nota sobre origem: o roadmap (`project_fase11_fichas_tecnicas`) reserva esta task para os "14
cenários listados no prompt [mestre]" -- mas o prompt mestre original não foi salvo verbatim em
lugar nenhum do repositório, só resumido no roadmap como uma lista de dimensões: "sem/com desenho,
sem/com logo, múltiplos aviamentos e tecidos, grades diferentes, custos completos e incompletos,
regeneração, aprovação, exportações, fidelidade visual". Os 14 testes abaixo são uma reconstrução
a partir dessas dimensões, não uma transcrição do texto original.

O que este arquivo cobre e o que não cobre:

- Mecânica de rota HTTP (404, 412, permissões, nome de arquivo) já está em `test_api_fichas.py`.
- Módulos individuais (extração, verificação, validação, template) já têm suíte própria.
- Aqui o alvo é a **combinação**: será que a ficha inteira -- dados variados, logo, desenho,
  grade, custos -- ainda produz um `.docx` fiel ao template (sem placeholder sobrando, sem tabela
  extra, sem imagem fantasma) quando várias dessas peças aparecem juntas? É o tipo de falha que
  testar cada módulo isoladamente não pega.

Os testes que exigem o PDF (contagem de página, texto extraído) usam o mesmo `skipUnless` que
`test_fichas_pdf.py` -- o CI não tem LibreOffice instalado.
"""

import io
import os
import re
import shutil
import tempfile
import unittest

from docx import Document
from PIL import Image

import fichas_desenho as fdz
import fichas_docx as fd
import fichas_logo as fl
import fichas_modelo as fm
import fichas_pdf as fp
import fichas_template as ft

TENANT_TESTE = "teste_task19_cenarios_e2e"
FICHA_TESTE = "99999999-9999-9999-9999-999999999999"

TEM_LIBREOFFICE = fp.libreoffice_disponivel()
MOTIVO_PULO = "LibreOffice não instalado neste ambiente"

REGEX_PLACEHOLDER = re.compile(r"\{\{.*?\}\}|\{%.*?%\}")

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _campo(valor):
    return {"valor": valor, "origem": fm.ORIGEM_FORNECIDO, "trecho": ""}


def _ficha_base(id_ficha: str = FICHA_TESTE) -> dict:
    ficha = fm.ficha_vazia()
    ficha["id"] = id_ficha
    d = ficha["dados"]
    d["ficha"]["ref"] = _campo("CM-019")
    d["ficha"]["nome"] = _campo("Camisa Social Branca")
    d["ficha"]["colecao"] = _campo("Verão 2027")
    d["ficha"]["descricao"] = _campo("Manga longa, gola italiana, botões de madrepérola")
    d["ficha"]["designer"] = _campo("Ana Paula")
    d["ficha"]["tecnica"] = _campo("Corte reto")
    d["ficha"]["empresa"] = _campo("SENAI LabFashion")
    d["ficha"]["data"] = _campo("15/09/2026")

    cor = fm.cor_beneficiamento_vazia()
    cor["item"] = _campo("1")
    cor["descricao"] = _campo("Corpo")
    cor["cor"] = _campo("Branco")
    cor["beneficiamento"] = _campo("Nenhum")
    d["cores_beneficiamentos"] = [cor]

    aviamento = fm.aviamento_vazio()
    aviamento["descricao"] = _campo("Botão madrepérola")
    aviamento["composicao"] = _campo("Madrepérola")
    aviamento["cor"] = _campo("Branco")
    aviamento["quantidade"] = _campo(8)
    aviamento["fornecedor"] = _campo("Botões & Cia")
    aviamento["preco"] = _campo(0.35)
    d["aviamentos"] = [aviamento]

    tecido = fm.tecido_vazio()
    tecido["descricao"] = _campo("Tricoline")
    tecido["composicao"] = _campo("100% algodão")
    tecido["cor"] = _campo("Branco")
    tecido["quantidade"] = _campo(1.5)
    tecido["largura"] = _campo(1.4)
    tecido["fornecedor"] = _campo("Tecelagem Sul")
    tecido["preco"] = _campo(18.9)
    d["tecidos"] = [tecido]

    operacao = fm.operacao_vazia()
    operacao["descricao"] = _campo("Costurar ombro")
    operacao["maquinas"] = _campo("Overlock")
    d["sequencia_operacional"] = [operacao]

    d["modelagem"]["modelista"] = _campo("Carla Souza")
    d["modelagem"]["numero_moldes"] = _campo(6)
    parte = fm.parte_modelagem_vazia()
    parte["descricao"] = _campo("Frente")
    d["modelagem"]["partes"] = [parte]

    return ficha


class TestCenariosBase(unittest.TestCase):
    """Base comum: diretório temporário para os .docx/.pdf gerados e limpeza do tenant fictício
    (pasta da ficha + branding), para os testes não sujarem `tenant_data/` de verdade."""

    def setUp(self):
        self.diretorio = tempfile.mkdtemp()
        self._limpar_tenant()

    def tearDown(self):
        shutil.rmtree(self.diretorio, ignore_errors=True)
        self._limpar_tenant()

    def _limpar_tenant(self):
        import fichas_repo as fr

        pasta_ficha = fr._dir_ficha(TENANT_TESTE, FICHA_TESTE)
        if os.path.isdir(pasta_ficha):
            shutil.rmtree(pasta_ficha, ignore_errors=True)
        for sufixo in ("_logo.png", "_logo.json"):
            caminho = os.path.join(fl.DIRETORIO_BRANDING, f"{TENANT_TESTE}{sufixo}")
            if os.path.exists(caminho):
                os.remove(caminho)

    def _renderizar(self, ficha, nome_arquivo="ficha.docx", tenant_id=None) -> str:
        caminho = os.path.join(self.diretorio, nome_arquivo)
        return fd.renderizar_para_arquivo(ficha, caminho, tenant_id=tenant_id)

    def _texto(self, caminho: str) -> str:
        doc = Document(caminho)
        partes = [p.text for p in doc.paragraphs]
        for tabela in doc.tables:
            for linha in tabela.rows:
                partes.extend(celula.text for celula in linha.cells)
        return "\n".join(partes)

    def _sem_placeholder_sobrando(self, caminho: str):
        sobrou = REGEX_PLACEHOLDER.findall(self._texto(caminho))
        self.assertEqual(sobrou, [], f"Placeholder(s) sem substituir: {sobrou}")

    def _mesmo_numero_de_tabelas_do_template(self, caminho: str):
        self.assertEqual(
            len(Document(caminho).tables), len(Document(ft.CAMINHO_TEMPLATE).tables),
            "O documento final criou ou perdeu uma tabela em relação ao template.",
        )

    def _aprovar_desenho(self, ficha, conteudo=PNG_1X1, versao=1):
        versoes = ficha["desenho"]["versoes"]
        versoes.append({
            "versao": versao, "prompt_visual": "x", "instrucoes_acumuladas": "",
            "status": fm.DESENHO_AGUARDANDO_APROVACAO, "criado_em": "",
        })
        ficha["desenho"]["solicitado"] = True
        fdz.salvar_desenho(TENANT_TESTE, ficha["id"], versao, conteudo)
        return fdz.aprovar_versao(ficha, versao)

    def _logo_png(self, largura=300, altura=180, cor=(200, 30, 30, 255)) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGBA", (largura, altura), cor).save(buffer, format="PNG")
        return buffer.getvalue()


# --- 1-5: matriz logo x desenho ------------------------------------------------------------------

class TestMatrizLogoEDesenho(TestCenariosBase):

    def test_01_ficha_minima_sem_nada_renderiza_limpa(self):
        # O caso mais comum no início do fluxo: ficha recém-criada, quase tudo em branco, sem
        # logo cadastrado e sem desenho solicitado.
        caminho = self._renderizar(fm.ficha_vazia(), tenant_id=TENANT_TESTE)
        self._sem_placeholder_sobrando(caminho)
        self._mesmo_numero_de_tabelas_do_template(caminho)
        self.assertEqual(len(Document(caminho).inline_shapes), 0)

    def test_02_ficha_completa_sem_logo_sem_desenho(self):
        caminho = self._renderizar(_ficha_base(), tenant_id=TENANT_TESTE)
        self._sem_placeholder_sobrando(caminho)
        texto = self._texto(caminho)
        for esperado in ("CM-019", "Camisa Social Branca", "Ana Paula", "Tricoline"):
            with self.subTest(valor=esperado):
                self.assertIn(esperado, texto)
        self.assertEqual(len(Document(caminho).inline_shapes), 0)

    def test_03_ficha_completa_com_logo_sem_desenho(self):
        fl.salvar_logo(TENANT_TESTE, self._logo_png())
        caminho = self._renderizar(_ficha_base(), tenant_id=TENANT_TESTE)
        self._sem_placeholder_sobrando(caminho)
        self.assertEqual(len(Document(caminho).inline_shapes), 1)

    def test_04_ficha_completa_com_desenho_aprovado_sem_logo(self):
        ficha = self._aprovar_desenho(_ficha_base())
        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        self._sem_placeholder_sobrando(caminho)
        self.assertEqual(len(Document(caminho).inline_shapes), 1)

    def test_05_ficha_completa_com_logo_e_desenho_juntos(self):
        # As duas imagens entram no mesmo documento sem uma atropelar a outra -- risco real porque
        # ambas passam pelo mesmo InlineImage/DocxTemplate.
        fl.salvar_logo(TENANT_TESTE, self._logo_png())
        ficha = self._aprovar_desenho(_ficha_base())
        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        self._sem_placeholder_sobrando(caminho)
        self._mesmo_numero_de_tabelas_do_template(caminho)
        self.assertEqual(len(Document(caminho).inline_shapes), 2)


# --- 6: múltiplos aviamentos e tecidos ------------------------------------------------------------

class TestListasDinamicas(TestCenariosBase):

    def test_06_muitos_aviamentos_e_tecidos_crescem_as_tabelas(self):
        ficha = _ficha_base()
        for i in range(6):
            aviamento = fm.aviamento_vazio()
            aviamento["descricao"] = _campo(f"Aviamento extra {i}")
            ficha["dados"]["aviamentos"].append(aviamento)
        for i in range(6):
            tecido = fm.tecido_vazio()
            tecido["descricao"] = _campo(f"Tecido extra {i}")
            ficha["dados"]["tecidos"].append(tecido)

        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        self._sem_placeholder_sobrando(caminho)
        texto = self._texto(caminho)
        for i in range(6):
            with self.subTest(item=i):
                self.assertIn(f"Aviamento extra {i}", texto)
                self.assertIn(f"Tecido extra {i}", texto)


# --- 7-9: grades diferentes ------------------------------------------------------------------------

class TestGradesDiferentes(TestCenariosBase):

    def test_07_grade_somente_comercial(self):
        ficha = _ficha_base()
        ficha["dados"]["grade"]["comerciais"] = _campo(["P", "M", "G"])
        ficha["dados"]["grade"]["numericos"] = _campo([])
        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        texto = self._texto(caminho)
        self.assertEqual(texto.count(ft.MARCA_SELECIONADO), 3)

    def test_08_grade_somente_numerica(self):
        ficha = _ficha_base()
        ficha["dados"]["grade"]["comerciais"] = _campo([])
        ficha["dados"]["grade"]["numericos"] = _campo(["38", "40", "42", "44"])
        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        texto = self._texto(caminho)
        self.assertEqual(texto.count(ft.MARCA_SELECIONADO), 4)

    def test_09_grade_todos_os_18_tamanhos_marcados(self):
        ficha = _ficha_base()
        ficha["dados"]["grade"]["comerciais"] = _campo(list(fm.TAMANHOS_COMERCIAIS))
        ficha["dados"]["grade"]["numericos"] = _campo(list(fm.TAMANHOS_NUMERICOS))
        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        texto = self._texto(caminho)
        self.assertEqual(
            texto.count(ft.MARCA_SELECIONADO), len(ft.TAMANHOS_GRADE)
        )
        self.assertEqual(texto.count(ft.MARCA_NAO_SELECIONADO), 0)


# --- 10-11: custos completos e incompletos ----------------------------------------------------

class TestCustos(TestCenariosBase):

    def test_10_custos_completos_aparecem_formatados_em_padrao_brasileiro(self):
        ficha = _ficha_base()
        custos = ficha["dados"]["custos"]
        custos["aviamentos"]["custo"] = _campo(2.8)
        custos["tecidos"]["custo"] = _campo(28.35)
        custos["costura_beneficiamento"]["custo"] = _campo(15)
        custos["outros"]["custo"] = _campo(0)
        custos["preco_total"]["custo"] = _campo(1234.5)

        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        texto = self._texto(caminho)
        for esperado in ("2,80", "28,35", "15,00", "0,00", "1.234,50"):
            with self.subTest(valor=esperado):
                self.assertIn(esperado, texto)

    def test_11_custos_incompletos_saem_em_branco_nunca_none_ou_zero_falso(self):
        # Regra de não-invenção vale também na impressão: custo sem informação é branco, não "0"
        # (que pareceria "confirmado gratuito") nem "None" (que vazaria detalhe de implementação).
        ficha = _ficha_base()
        ficha["dados"]["custos"]["tecidos"]["custo"] = _campo(42.0)
        # aviamentos, costura, outros e total ficam None (o padrão de ficha_vazia())

        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        texto = self._texto(caminho)
        self.assertIn("42,00", texto)
        self.assertNotIn("None", texto)
        # "R$ " sem número atrás confirma que o campo saiu vazio, não zerado
        self.assertRegex(texto, r"R\$\s*\n")


# --- 12-13: regeneração e aprovação de desenho ------------------------------------------------

class TestRegeneracaoEAprovacaoDeDesenho(TestCenariosBase):

    def _png(self, cor) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGBA", (64, 64), cor).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_12_regeneracao_acumula_instrucao_e_gera_v2_distinta_de_v1(self):
        ficha = _ficha_base()
        fdz.salvar_desenho(TENANT_TESTE, ficha["id"], 1, self._png((255, 0, 0, 255)))
        ficha["desenho"]["versoes"] = [{
            "versao": 1, "prompt_visual": "camisa branca",
            "instrucoes_acumuladas": "manga 3/4", "status": fm.DESENHO_AGUARDANDO_APROVACAO,
            "criado_em": "",
        }]

        acumuladas = fdz.acumular_instrucao("manga 3/4", "gola mais alta")
        self.assertIn("manga 3/4", acumuladas)
        self.assertIn("gola mais alta", acumuladas)

        fdz.salvar_desenho(TENANT_TESTE, ficha["id"], 2, self._png((0, 0, 255, 255)))
        ficha["desenho"]["versoes"].append({
            "versao": 2, "prompt_visual": "camisa branca ajustada",
            "instrucoes_acumuladas": acumuladas, "status": fm.DESENHO_AGUARDANDO_APROVACAO,
            "criado_em": "",
        })

        # Nenhuma das duas está aprovada ainda -- o documento sai sem imagem nenhuma.
        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        self.assertEqual(len(Document(caminho).inline_shapes), 0)

        ficha = fdz.aprovar_versao(ficha, 2)
        caminho = self._renderizar(ficha, "com_v2.docx", tenant_id=TENANT_TESTE)
        self.assertEqual(len(Document(caminho).inline_shapes), 1)
        self.assertEqual(
            fdz.caminho_desenho_aprovado(TENANT_TESTE, ficha),
            fdz.caminho_desenho(TENANT_TESTE, ficha["id"], 2),
        )

    def test_13_troca_de_versao_aprovada_reflete_no_documento(self):
        ficha = self._aprovar_desenho(_ficha_base(), conteudo=self._png((255, 0, 0, 255)), versao=1)
        fdz.salvar_desenho(TENANT_TESTE, ficha["id"], 2, self._png((0, 0, 255, 255)))
        ficha["desenho"]["versoes"].append({
            "versao": 2, "prompt_visual": "x", "instrucoes_acumuladas": "",
            "status": fm.DESENHO_AGUARDANDO_APROVACAO, "criado_em": "",
        })

        # Ainda vale v1: o documento usa o arquivo de v1.
        self.assertEqual(
            fdz.caminho_desenho_aprovado(TENANT_TESTE, ficha),
            fdz.caminho_desenho(TENANT_TESTE, ficha["id"], 1),
        )

        # Usuário aprova v2 -- v1 é rebaixada, e o documento passa a usar v2.
        ficha = fdz.aprovar_versao(ficha, 2)
        self.assertEqual(ficha["desenho"]["versoes"][0]["status"], fm.DESENHO_AGUARDANDO_APROVACAO)
        self.assertEqual(
            fdz.caminho_desenho_aprovado(TENANT_TESTE, ficha),
            fdz.caminho_desenho(TENANT_TESTE, ficha["id"], 2),
        )
        caminho = self._renderizar(ficha, tenant_id=TENANT_TESTE)
        self.assertEqual(len(Document(caminho).inline_shapes), 1)


# --- 14: fidelidade visual, via PDF real --------------------------------------------------------

@unittest.skipUnless(TEM_LIBREOFFICE, MOTIVO_PULO)
class TestFidelidadeVisualNoPdf(TestCenariosBase):
    """A verificação final de fidelidade -- estrutural (docx) não garante fidelidade visual
    (PDF): fonte ausente ou célula que estourou podem transformar 3 páginas em 4 sem nenhum erro
    de render. Só o PDF de verdade prova isso."""

    def test_14_ficha_completa_com_logo_e_desenho_gera_pdf_fiel_sem_pagina_extra(self):
        from pypdf import PdfReader

        def _ficha_grade():
            ficha = _ficha_base()
            ficha["dados"]["grade"]["comerciais"] = _campo(["P", "M", "G"])
            ficha["dados"]["grade"]["numericos"] = _campo(["38", "40"])
            return ficha

        # Referência: a mesma ficha, sem logo e sem desenho -- para provar que acrescentar as
        # duas imagens não empurra a ficha para uma página a mais (o próprio risco que
        # ALTURA_MAX_DESENHO_CM/ALTURA_MAX_CM foram dimensionados para evitar).
        docx_referencia = self._renderizar(_ficha_grade(), "referencia.docx", tenant_id=TENANT_TESTE)
        pdf_referencia = os.path.join(self.diretorio, "referencia.pdf")
        fp.converter_para_pdf(docx_referencia, pdf_referencia)
        paginas_referencia = fp.contar_paginas(pdf_referencia)

        fl.salvar_logo(TENANT_TESTE, self._logo_png())
        ficha = self._aprovar_desenho(_ficha_grade())
        docx = self._renderizar(ficha, "com_imagens.docx", tenant_id=TENANT_TESTE)
        pdf = os.path.join(self.diretorio, "com_imagens.pdf")
        fp.converter_para_pdf(docx, pdf)

        with open(pdf, "rb") as arquivo:
            self.assertTrue(arquivo.read(5).startswith(b"%PDF-"))

        self.assertEqual(
            fp.contar_paginas(pdf), paginas_referencia,
            "Logo + desenho aprovado mudaram a paginação da ficha -- uma das duas áreas estourou.",
        )

        texto = "\n".join(pagina.extract_text() or "" for pagina in PdfReader(pdf).pages)
        for esperado in ("CM-019", "Camisa Social Branca", "TAMANHOS COMERCIAIS", "TAMANHOS NUMÉRICOS"):
            with self.subTest(valor=esperado):
                self.assertIn(esperado, texto)


if __name__ == "__main__":
    unittest.main()
