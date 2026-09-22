# -*- coding: utf-8 -*-
"""Testes do render da ficha no template .docx (Fase 11, Task 10).

A classe TestRenderCompleto é o teste mais valioso do arquivo: renderiza contra o template de
produção de verdade e confere que nenhum placeholder sobrou sem substituir. É a única forma de
pegar uma incompatibilidade entre o contexto (este módulo) e o .docx (Task 9) -- um `{{ ref }}`
que ninguém alimenta não gera erro no docxtpl, só sai impresso literalmente na ficha.
"""

import os
import re
import shutil
import tempfile
import unittest

from docx import Document

import fichas_desenho as fdz
import fichas_docx as fd
import fichas_modelo as fm
import fichas_repo as fr
import fichas_template as ft

# PNG 1x1 válido -- o conteúdo da imagem não importa aqui, só que o Pillow consiga abri-la e que o
# docxtpl a embuta no arquivo final.
PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

REGEX_PLACEHOLDER = re.compile(r"\{\{.*?\}\}|\{%.*?%\}")


def _campo(valor):
    return {"valor": valor, "origem": fm.ORIGEM_FORNECIDO, "trecho": ""}


def _ficha_preenchida() -> dict:
    ficha = fm.ficha_vazia()
    ficha["id"] = "11111111-1111-1111-1111-111111111111"
    dados = ficha["dados"]

    dados["ficha"]["ref"] = _campo("CM-001")
    dados["ficha"]["nome"] = _campo("Camisa Social Branca")
    dados["ficha"]["colecao"] = _campo("Verão 2027")
    dados["ficha"]["descricao"] = _campo("Camisa social manga longa")
    dados["ficha"]["designer"] = _campo("Ana Paula")
    dados["ficha"]["tecnica"] = _campo("Alfaiataria")
    dados["ficha"]["empresa"] = _campo("SENAI LabFashion")
    dados["ficha"]["data"] = _campo("14/09/2026")

    dados["grade"]["numericos"] = _campo(["38", "40"])
    dados["grade"]["comerciais"] = _campo(["M"])

    aviamento = fm.aviamento_vazio()
    aviamento["descricao"] = _campo("Botão")
    aviamento["quantidade"] = _campo(10)
    aviamento["preco"] = _campo(0.5)
    dados["aviamentos"] = [aviamento]

    tecido = fm.tecido_vazio()
    tecido["descricao"] = _campo("Tricoline")
    tecido["composicao"] = _campo("100% algodão")
    tecido["quantidade"] = _campo(1.5)
    tecido["largura"] = _campo(1.5)
    tecido["preco"] = _campo(28.0)
    dados["tecidos"] = [tecido]

    cor = fm.cor_beneficiamento_vazia()
    cor["item"] = _campo("Corpo")
    cor["cor"] = _campo("Branco")
    dados["cores_beneficiamentos"] = [cor]

    dados["custos"]["aviamentos"]["custo"] = _campo(13.3)
    dados["custos"]["tecidos"]["custo"] = _campo(42.0)
    dados["custos"]["costura_beneficiamento"]["custo"] = _campo(25.0)
    dados["custos"]["outros"]["custo"] = _campo(0.0)
    dados["custos"]["preco_total"]["custo"] = _campo(80.3)
    dados["custos"]["aviamentos"]["observacao"] = _campo("cotação set/26")

    operacao = fm.operacao_vazia()
    operacao["descricao"] = _campo("Fechar ombros")
    operacao["maquinas"] = _campo("Overloque")
    dados["sequencia_operacional"] = [operacao]

    dados["modelagem"]["modelista"] = _campo("Carla Souza")
    dados["modelagem"]["numero_moldes"] = _campo(8)
    parte = fm.parte_modelagem_vazia()
    parte["descricao"] = _campo("Frente")
    parte["observacoes"] = _campo("cortar 2x")
    dados["modelagem"]["partes"] = [parte]

    return ficha


class TestFormatacaoDeNumeros(unittest.TestCase):
    """Padrão brasileiro sem depender de locale instalado -- servidor Linux enxuto costuma não ter
    pt_BR, e o documento precisa sair correto de qualquer jeito."""

    def test_dinheiro_sempre_com_duas_casas(self):
        self.assertEqual(fd._formatar_dinheiro(80.3), "80,30")
        self.assertEqual(fd._formatar_dinheiro(0), "0,00")

    def test_dinheiro_com_separador_de_milhar(self):
        self.assertEqual(fd._formatar_dinheiro(1234.5), "1.234,50")
        self.assertEqual(fd._formatar_dinheiro(1234567.89), "1.234.567,89")

    def test_dinheiro_ausente_vira_vazio(self):
        self.assertEqual(fd._formatar_dinheiro(None), "")
        self.assertEqual(fd._formatar_dinheiro(""), "")

    def test_quantidade_inteira_sem_casas(self):
        # "10,00 botões" carregaria uma precisão que o dado não tem.
        self.assertEqual(fd._formatar_quantidade(10), "10")
        self.assertEqual(fd._formatar_quantidade(10.0), "10")

    def test_quantidade_fracionada_usa_virgula(self):
        self.assertEqual(fd._formatar_quantidade(1.5), "1,5")
        self.assertEqual(fd._formatar_quantidade(1.25), "1,25")

    def test_quantidade_ausente_vira_vazio(self):
        self.assertEqual(fd._formatar_quantidade(None), "")


class TestContexto(unittest.TestCase):

    def test_ficha_vazia_nao_produz_none_em_lugar_nenhum(self):
        # Regra de não-invenção também na impressão: campo sem informação sai em branco, nunca
        # "None" nem "0" -- que o leitor interpretaria como dado real.
        contexto = fd.montar_contexto(fm.ficha_vazia())

        def sem_none(valor, caminho):
            if isinstance(valor, dict):
                for chave, sub in valor.items():
                    sem_none(sub, f"{caminho}.{chave}")
            elif isinstance(valor, list):
                for i, item in enumerate(valor):
                    sem_none(item, f"{caminho}[{i}]")
            else:
                self.assertNotIn("None", str(valor), f"'None' vazou para o documento em {caminho}")

        sem_none(contexto, "contexto")

    def test_campos_escalares_batem_com_o_contrato_do_template(self):
        contexto = fd.montar_contexto(fm.ficha_vazia())
        for nome in ft.PLACEHOLDERS_ESCALARES:
            with self.subTest(placeholder=nome):
                self.assertIn(nome, contexto, f"O template usa {{{{ {nome} }}}} e o contexto não fornece.")

    def test_listas_dinamicas_batem_com_o_contrato_do_template(self):
        contexto = fd.montar_contexto(fm.ficha_vazia())
        for nome in ft.PLACEHOLDERS_LISTA:
            with self.subTest(lista=nome):
                self.assertIn(nome, contexto)
                self.assertIsInstance(contexto[nome], list)

    def test_grade_marca_apenas_os_tamanhos_selecionados(self):
        contexto = fd.montar_contexto(_ficha_preenchida())
        grade = contexto["grade"]
        self.assertEqual(grade["38"], ft.MARCA_SELECIONADO)
        self.assertEqual(grade["40"], ft.MARCA_SELECIONADO)
        self.assertEqual(grade["M"], ft.MARCA_SELECIONADO)
        self.assertEqual(grade["34"], ft.MARCA_NAO_SELECIONADO)
        self.assertEqual(grade["XG"], ft.MARCA_NAO_SELECIONADO)

    def test_grade_cobre_todos_os_tamanhos(self):
        contexto = fd.montar_contexto(fm.ficha_vazia())
        self.assertEqual(set(contexto["grade"].keys()), set(ft.TAMANHOS_GRADE))

    def test_valores_formatados_na_tabela_de_aviamentos(self):
        contexto = fd.montar_contexto(_ficha_preenchida())
        aviamento = contexto["aviamentos"][0]
        self.assertEqual(aviamento["quantidade"], "10")
        self.assertEqual(aviamento["preco"], "0,50")


class TestPartesDaModelagemNuncaVazia(unittest.TestCase):
    """No template, modelista e quantidade de moldes são impressos na primeira iteração do laço
    das partes. Lista vazia => laço não roda => a linha some e leva os dois junto."""

    def test_lista_vazia_vira_uma_linha_em_branco(self):
        contexto = fd.montar_contexto(fm.ficha_vazia())
        self.assertEqual(len(contexto["partes"]), 1)
        self.assertEqual(contexto["partes"][0], {"descricao": "", "observacoes": ""})

    def test_modelista_sobrevive_a_ficha_sem_partes(self):
        ficha = fm.ficha_vazia()
        ficha["dados"]["modelagem"]["modelista"] = _campo("Carla Souza")
        ficha["dados"]["modelagem"]["numero_moldes"] = _campo(8)

        contexto = fd.montar_contexto(ficha)
        self.assertEqual(contexto["modelista"], "Carla Souza")
        self.assertEqual(contexto["numero_moldes"], "8")
        self.assertTrue(contexto["partes"], "sem linha nenhuma, modelista/moldes não seriam impressos")

    def test_lista_preenchida_e_preservada(self):
        contexto = fd.montar_contexto(_ficha_preenchida())
        self.assertEqual(len(contexto["partes"]), 1)
        self.assertEqual(contexto["partes"][0]["descricao"], "Frente")


def _ficha_com_medidas(numericos=(), comerciais=(), linhas=()):
    ficha = fm.ficha_vazia()
    ficha["dados"]["grade"]["numericos"] = _campo(list(numericos))
    ficha["dados"]["grade"]["comerciais"] = _campo(list(comerciais))
    ficha["dados"]["medidas"] = [
        {"ponto": _campo(ponto), "valores": {t: _campo(v) for t, v in valores.items()}}
        for ponto, valores in linhas
    ]
    return ficha


class TestMedidasNoContexto(unittest.TestCase):
    """Fase 14, Bloco M, Task 22 -- contexto pronto antes de o template usá-lo (Bloco T).

    O que mais importa aqui é o alinhamento posicional: cabeçalho e corpo da tabela são dois laços
    Jinja separados no Word, então valores[i] TEM que ser a medida de medidas_tamanhos[i].
    """

    def test_ficha_sem_medidas_nao_quebra(self):
        contexto = fd.montar_contexto(fm.ficha_vazia())
        self.assertEqual(contexto["medidas"], [])
        self.assertEqual(contexto["medidas_tamanhos"], [])

    def test_colunas_saem_da_grade_em_ordem_canonica(self):
        ficha = _ficha_com_medidas(numericos=["42", "38"], comerciais=["M"])
        self.assertEqual(fd.montar_contexto(ficha)["medidas_tamanhos"], ["38", "42", "M"])

    def test_valores_alinham_com_as_colunas(self):
        ficha = _ficha_com_medidas(
            numericos=["38", "40", "42"],
            linhas=[("Busto", {"40": 96.0, "38": 92.0, "42": 100.0})],  # fora de ordem de propósito
        )
        contexto = fd.montar_contexto(ficha)
        self.assertEqual(contexto["medidas_tamanhos"], ["38", "40", "42"])
        self.assertEqual(contexto["medidas"][0]["valores"], ["92", "96", "100"])

    def test_tamanho_sem_medida_vira_celula_vazia_na_posicao_certa(self):
        ficha = _ficha_com_medidas(
            numericos=["38", "40", "42"],
            linhas=[("Busto", {"38": 92.0, "42": 100.0})],  # 40 em branco
        )
        self.assertEqual(fd.montar_contexto(ficha)["medidas"][0]["valores"], ["92", "", "100"])

    def test_medida_de_tamanho_fora_da_grade_nao_entra(self):
        ficha = _ficha_com_medidas(
            numericos=["38"],
            linhas=[("Busto", {"38": 92.0, "44": 98.0})],
        )
        contexto = fd.montar_contexto(ficha)
        self.assertEqual(contexto["medidas_tamanhos"], ["38"])
        self.assertEqual(contexto["medidas"][0]["valores"], ["92"])

    def test_decimal_sai_no_padrao_brasileiro(self):
        ficha = _ficha_com_medidas(numericos=["38"], linhas=[("Ombro", {"38": 41.5})])
        self.assertEqual(fd.montar_contexto(ficha)["medidas"][0]["valores"], ["41,5"])

    def test_nunca_vaza_none_para_o_documento(self):
        ficha = _ficha_com_medidas(numericos=["38"], linhas=[("Ombro", {"38": None})])
        contexto = fd.montar_contexto(ficha)
        self.assertEqual(contexto["medidas"][0]["valores"], [""])

    def test_linha_totalmente_vazia_e_descartada(self):
        ficha = fm.ficha_vazia()
        ficha["dados"]["grade"]["numericos"] = _campo(["38"])
        ficha["dados"]["medidas"] = [fm.linha_medida_vazia(["38"])]
        self.assertEqual(fd.montar_contexto(ficha)["medidas"], [])

    def test_linha_so_com_ponto_e_mantida(self):
        # Ponto nomeado sem medida ainda é informação: o documento impresso mostra a linha
        # esperando preenchimento à mão, como no formulário original.
        ficha = _ficha_com_medidas(numericos=["38"], linhas=[("Ombro", {})])
        contexto = fd.montar_contexto(ficha)
        self.assertEqual(len(contexto["medidas"]), 1)
        self.assertEqual(contexto["medidas"][0]["ponto"], "Ombro")

    def test_grade_maior_que_o_limite_e_truncada_nas_colunas_do_documento(self):
        nove = ["34", "36", "38", "40", "42", "44", "46", "48", "50"]
        ficha = _ficha_com_medidas(
            numericos=nove,
            linhas=[("Busto", {t: 80.0 + i for i, t in enumerate(nove)})],
        )
        contexto = fd.montar_contexto(ficha)
        self.assertEqual(len(contexto["medidas_tamanhos"]), fm.MAX_COLUNAS_MEDIDAS)
        self.assertNotIn("50", contexto["medidas_tamanhos"])
        # Alinhamento tem que sobreviver ao truncamento.
        self.assertEqual(len(contexto["medidas"][0]["valores"]), fm.MAX_COLUNAS_MEDIDAS)

    def test_medidas_malformadas_nao_quebram_o_render(self):
        for medidas in ("nao e uma lista", [None], ["nao e um dict"], [{"valores": "nao e um dict"}]):
            with self.subTest(medidas=medidas):
                ficha = fm.ficha_vazia()
                ficha["dados"]["medidas"] = medidas
                fd.montar_contexto(ficha)  # não deve levantar


class TestPrecoSugeridoEAprovacaoNoContexto(unittest.TestCase):
    """Fase 14, Bloco T, Task 27 -- os três saem vazios quando não há o que mostrar, nunca "0,00"
    nem "None": no documento impresso um zero na linha de preço seria lido como "custa zero"."""

    def test_ficha_sem_custos_nao_imprime_preco(self):
        contexto = fd.montar_contexto(fm.ficha_vazia())
        self.assertEqual(contexto["preco_sugerido"], "")

    def test_preco_sugerido_usa_markup_divisor_e_padrao_brasileiro(self):
        ficha = fm.ficha_vazia()
        ficha["dados"]["custos"]["aviamentos"]["custo"] = _campo(100.0)
        ficha["precificacao"] = {
            "imposto_percentual": 10, "comissao_percentual": 15, "margem_lucro_percentual": 20,
        }
        # 100 / (1 - 0,45) = 181,818... -> "181,82"
        self.assertEqual(fd.montar_contexto(ficha)["preco_sugerido"], "181,82")

    def test_percentuais_impossiveis_nao_imprimem_preco(self):
        ficha = fm.ficha_vazia()
        ficha["dados"]["custos"]["aviamentos"]["custo"] = _campo(100.0)
        ficha["precificacao"] = {
            "imposto_percentual": 0, "comissao_percentual": 0, "margem_lucro_percentual": 100,
        }
        self.assertEqual(fd.montar_contexto(ficha)["preco_sugerido"], "")

    def test_ficha_nao_aprovada_tem_carimbo_vazio(self):
        contexto = fd.montar_contexto(fm.ficha_vazia())
        self.assertEqual(contexto["aprovada_por"], "")
        self.assertEqual(contexto["aprovada_em"], "")

    def test_aprovacao_sai_com_data_legivel(self):
        ficha = fm.ficha_vazia()
        ficha["aprovacao"] = {
            "aprovada_por": "Ana Paula", "aprovada_em": "2026-09-22T14:30:00",
            "observacao": "", "historico": [],
        }
        contexto = fd.montar_contexto(ficha)
        self.assertEqual(contexto["aprovada_por"], "Ana Paula")
        self.assertEqual(contexto["aprovada_em"], "22/09/2026 14:30")

    def test_data_ilegivel_nao_vaza_para_o_documento(self):
        ficha = fm.ficha_vazia()
        ficha["aprovacao"] = {"aprovada_por": "X", "aprovada_em": "nao e uma data",
                              "observacao": "", "historico": []}
        self.assertEqual(fd.montar_contexto(ficha)["aprovada_em"], "")

    def test_ficha_antiga_sem_chave_aprovacao_nao_quebra(self):
        ficha = fm.ficha_vazia()
        del ficha["aprovacao"]
        contexto = fd.montar_contexto(ficha)
        self.assertEqual(contexto["aprovada_por"], "")


class TestRenderCompleto(unittest.TestCase):
    """Render de verdade contra o template de produção."""

    def setUp(self):
        self.diretorio = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.diretorio, ignore_errors=True)

    def _renderizar(self, ficha) -> str:
        caminho = os.path.join(self.diretorio, "ficha.docx")
        return fd.renderizar_para_arquivo(ficha, caminho)

    def _texto_do_documento(self, caminho: str) -> str:
        doc = Document(caminho)
        partes = [p.text for p in doc.paragraphs]
        for tabela in doc.tables:
            for linha in tabela.rows:
                partes.extend(celula.text for celula in linha.cells)
        return "\n".join(partes)

    def test_ficha_preenchida_nao_deixa_placeholder_literal(self):
        caminho = self._renderizar(_ficha_preenchida())
        sobrou = REGEX_PLACEHOLDER.findall(self._texto_do_documento(caminho))
        self.assertEqual(sobrou, [], f"Placeholder(s) sem substituir no documento final: {sobrou}")

    def test_ficha_vazia_tambem_renderiza(self):
        # O caso mais comum no começo do fluxo: ficha recém-criada, quase tudo em branco. Não pode
        # explodir nem imprimir placeholder.
        caminho = self._renderizar(fm.ficha_vazia())
        sobrou = REGEX_PLACEHOLDER.findall(self._texto_do_documento(caminho))
        self.assertEqual(sobrou, [])

    def test_dados_aparecem_no_documento(self):
        caminho = self._renderizar(_ficha_preenchida())
        texto = self._texto_do_documento(caminho)
        for esperado in ("CM-001", "Camisa Social Branca", "Ana Paula", "Carla Souza", "Tricoline"):
            with self.subTest(valor=esperado):
                self.assertIn(esperado, texto)

    def test_tabelas_dinamicas_crescem_conforme_os_dados(self):
        ficha = _ficha_preenchida()
        for indice in range(4):  # 1 original + 4 = 5 aviamentos
            aviamento = fm.aviamento_vazio()
            aviamento["descricao"] = _campo(f"Aviamento {indice}")
            ficha["dados"]["aviamentos"].append(aviamento)

        caminho = self._renderizar(ficha)
        texto = self._texto_do_documento(caminho)
        for indice in range(4):
            self.assertIn(f"Aviamento {indice}", texto)

    def test_sequencia_operacional_e_numerada_pelo_template(self):
        ficha = _ficha_preenchida()
        for descricao in ("Preparar frente", "Aplicar gola"):
            operacao = fm.operacao_vazia()
            operacao["descricao"] = _campo(descricao)
            ficha["dados"]["sequencia_operacional"].append(operacao)

        doc = Document(self._renderizar(ficha))
        tabela = next(
            t for t in doc.tables
            if t.rows[0].cells[0].text.strip().upper() == "ETAPA"
        )
        numeros = [linha.cells[0].text.strip() for linha in tabela.rows[1:]]
        self.assertEqual(numeros, ["1", "2", "3"])

    def test_caractere_especial_nao_corrompe_o_xml(self):
        # "Pano & Cia" e observações com "<" quebrariam o XML do .docx sem autoescape, e o Word
        # recusaria abrir o arquivo com "conteúdo ilegível". O teste só passa se o documento
        # gerado for relido com sucesso e o texto sair legível.
        ficha = _ficha_preenchida()
        ficha["dados"]["aviamentos"][0]["fornecedor"] = _campo("Pano & Cia <Ltda>")

        texto = self._texto_do_documento(self._renderizar(ficha))
        self.assertIn("Pano & Cia <Ltda>", texto)

    def test_contexto_incompleto_falha_alto(self):
        # Prova que o StrictUndefined está ativo: sem ele, uma variável que o contexto esqueceu
        # viraria campo em branco no documento, sem erro nenhum. Exige a exceção específica do
        # Jinja -- assertRaises(Exception) passaria por qualquer falha, inclusive uma não
        # relacionada, e daria uma falsa sensação de cobertura.
        from unittest.mock import patch

        from jinja2.exceptions import UndefinedError

        contexto_incompleto = fd.montar_contexto(_ficha_preenchida())
        del contexto_incompleto["ref"]

        with patch.object(fd, "montar_contexto", return_value=contexto_incompleto):
            with self.assertRaises(UndefinedError):
                self._renderizar(_ficha_preenchida())

    def test_documento_final_mantem_as_tabelas_do_template(self):
        # Fidelidade ao modelo: o render preenche, não reconstrói. Se o número de tabelas mudar,
        # alguma coisa está criando estrutura em vez de preencher a existente.
        doc_modelo = Document(ft.CAMINHO_TEMPLATE)
        doc_final = Document(self._renderizar(_ficha_preenchida()))
        self.assertEqual(len(doc_final.tables), len(doc_modelo.tables))


class TestDesenhoNoDocumento(unittest.TestCase):
    """Task 18: o desenho aprovado é embutido no .docx; qualquer outro estado sai em branco.

    Estes testes olham as imagens embutidas no arquivo final (não o contexto do render), porque é
    isso que o usuário recebe -- um contexto correto que não vira imagem no documento seria uma
    falha invisível para qualquer teste que parasse antes do `save()`.
    """

    TENANT = "teste_task18_desenho_docx"
    FICHA_ID = "77777777-7777-7777-7777-777777777777"

    def setUp(self):
        self.diretorio = tempfile.mkdtemp()
        self._limpar()

    def tearDown(self):
        shutil.rmtree(self.diretorio, ignore_errors=True)
        self._limpar()

    def _limpar(self):
        pasta = fr._dir_ficha(self.TENANT, self.FICHA_ID)
        if os.path.isdir(pasta):
            shutil.rmtree(pasta, ignore_errors=True)

    def _ficha_com_desenho(self, aprovar: bool):
        ficha = _ficha_preenchida()
        ficha["id"] = self.FICHA_ID
        ficha["desenho"]["solicitado"] = True
        ficha["desenho"]["versoes"] = [{
            "versao": 1, "prompt_visual": "x", "instrucoes_acumuladas": "",
            "status": fm.DESENHO_AGUARDANDO_APROVACAO, "criado_em": "",
        }]
        fdz.salvar_desenho(self.TENANT, self.FICHA_ID, 1, PNG_1X1)
        return fdz.aprovar_versao(ficha, 1) if aprovar else ficha

    def _imagens_embutidas(self, ficha) -> int:
        caminho = os.path.join(self.diretorio, "ficha.docx")
        fd.renderizar_para_arquivo(ficha, caminho, tenant_id=self.TENANT)
        return len(Document(caminho).inline_shapes)

    def test_desenho_aprovado_entra_no_documento(self):
        self.assertEqual(self._imagens_embutidas(self._ficha_com_desenho(aprovar=True)), 1)

    def test_desenho_nao_aprovado_nao_entra(self):
        self.assertEqual(self._imagens_embutidas(self._ficha_com_desenho(aprovar=False)), 0)

    def test_ficha_sem_desenho_renderiza_a_caixa_vazia(self):
        ficha = _ficha_preenchida()
        ficha["id"] = self.FICHA_ID
        self.assertEqual(self._imagens_embutidas(ficha), 0)

    def test_desenho_nao_altera_a_estrutura_do_template(self):
        # A imagem entra dentro da célula reservada -- não pode criar tabela, nem seção, nem
        # empurrar o layout. Contagem de tabelas é o sinal mais barato de que isso aconteceu.
        caminho = os.path.join(self.diretorio, "ficha.docx")
        fd.renderizar_para_arquivo(
            self._ficha_com_desenho(aprovar=True), caminho, tenant_id=self.TENANT
        )
        self.assertEqual(
            len(Document(caminho).tables), len(Document(ft.CAMINHO_TEMPLATE).tables)
        )

    def test_render_sem_tenant_nunca_embute_imagem(self):
        # Sem tenant não há de onde resolver logo nem desenho; o documento precisa sair mesmo
        # assim, com as duas áreas em branco.
        ficha = self._ficha_com_desenho(aprovar=True)
        caminho = os.path.join(self.diretorio, "sem_tenant.docx")
        fd.renderizar_para_arquivo(ficha, caminho)
        self.assertEqual(len(Document(caminho).inline_shapes), 0)


if __name__ == "__main__":
    unittest.main()
