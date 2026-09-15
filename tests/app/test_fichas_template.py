# -*- coding: utf-8 -*-
"""Testes do template .docx anotado (Fase 11, Task 9).

Estes testes rodam contra o arquivo de produção (`templates/ficha_tecnica_v1.docx`), não contra
uma fixture separada, e isso é de propósito: o template é um binário que qualquer pessoa pode
abrir no Word e salvar de volta. A falha que eles existem para pegar é justamente essa --

    alguém abre o .docx, ajusta uma borda, salva; o Word reescreve a célula fatiando
    `{{ ref }}` em dois runs; o docxtpl deixa de reconhecer o placeholder; a ficha sai impressa
    com "{{ ref }}" literal no lugar da referência -- sem erro, sem exceção, sem log.

Nenhuma biblioteca avisa sobre isso. O CI, com estes testes, avisa.
"""

import copy
import os
import shutil
import tempfile
import unittest

from docx import Document

import fichas_template as ft


class TestTemplateExiste(unittest.TestCase):

    def test_arquivo_existe(self):
        self.assertTrue(
            os.path.exists(ft.CAMINHO_TEMPLATE),
            f"O template de produção sumiu de {ft.CAMINHO_TEMPLATE}",
        )


class TestIntegridadeDosPlaceholders(unittest.TestCase):
    """A checagem central: nenhum placeholder pode estar fatiado entre runs."""

    @classmethod
    def setUpClass(cls):
        cls.inspecao = ft.inspecionar_template()

    def test_nenhum_placeholder_quebrado_por_run_splitting(self):
        quebrados = self.inspecao["quebrados"]
        self.assertEqual(
            quebrados, [],
            "Placeholder(s) fatiado(s) entre runs -- o docxtpl não vai substituí-los e eles "
            f"sairão literais no documento final:\n{quebrados}\n"
            "Causa provável: o template foi editado no Word. Para corrigir, reescreva a célula "
            "afetada via python-docx (ver scripts/anotar_template.py) em vez de digitar no Word.",
        )

    def test_template_tem_placeholders(self):
        # Guarda contra o caso extremo de alguém substituir o template pelo formulário em branco
        # original (sem anotação nenhuma) -- o render sairia mudo, sem erro.
        self.assertGreater(len(self.inspecao["placeholders"]), 0)


class TestContratoComORender(unittest.TestCase):
    """O template e o render (Task 10) precisam concordar sobre quais variáveis existem. Estes
    testes amarram os dois lados: mexer num sem mexer no outro quebra aqui."""

    @classmethod
    def setUpClass(cls):
        cls.inspecao = ft.inspecionar_template()

    def test_todos_os_escalares_esperados_estao_no_template(self):
        for nome in ft.PLACEHOLDERS_ESCALARES:
            with self.subTest(placeholder=nome):
                self.assertIn(
                    nome, self.inspecao["variaveis"],
                    f"O template não usa mais {{{{ {nome} }}}} -- o dado deixaria de ser impresso.",
                )

    def test_todas_as_listas_dinamicas_estao_no_template(self):
        self.assertEqual(self.inspecao["listas"], set(ft.PLACEHOLDERS_LISTA))

    def test_grade_e_usada_como_dicionario(self):
        self.assertIn("grade", self.inspecao["variaveis"])

    def test_todo_tamanho_da_grade_tem_celula_propria(self):
        # A grade foi diagramada em duas tabelas (34-44 numa, 46-56 noutra) -- fácil esquecer um
        # tamanho no meio do caminho e ele simplesmente nunca aparecer marcado na ficha impressa.
        placeholders = " ".join(self.inspecao["placeholders"])
        for tamanho in ft.TAMANHOS_GRADE:
            with self.subTest(tamanho=tamanho):
                self.assertIn(f"grade['{tamanho}']", placeholders)


class TestRotulosDaGrade(unittest.TestCase):
    """A grade impressa precisa dizer onde acaba o bloco de tamanhos comerciais e começa o numérico.

    O formulário original diagramou PP..XG e 34..56 numa faixa contínua de colunas, sem nada
    separando os dois grupos -- quem lê a ficha impressa não tem como saber que "P" e "42" são
    sistemas de numeração diferentes. Estes testes amarram o rótulo à coluna: se alguém reordenar
    os tamanhos no template, o rótulo deixa de bater e o teste acusa.
    """

    ROTULO_COMERCIAL = "TAMANHOS COMERCIAIS"
    ROTULO_NUMERICO = "TAMANHOS NUMÉRICOS"

    @classmethod
    def setUpClass(cls):
        cls.doc = Document(ft.CAMINHO_TEMPLATE)

    def _tabelas_da_grade(self):
        """As tabelas que contêm placeholders `grade[...]`, achadas por conteúdo (não por índice:
        inserir qualquer tabela antes delas deslocaria a numeração)."""
        tabelas = [
            tabela for tabela in self.doc.tables
            if any("grade[" in celula.text for linha in tabela.rows for celula in linha.cells)
        ]
        self.assertTrue(tabelas, "Nenhuma tabela do template contém placeholders da grade.")
        return tabelas

    def test_cada_tamanho_tem_o_rotulo_do_seu_grupo_acima(self):
        for tabela in self._tabelas_da_grade():
            rotulos = [celula.text.strip() for celula in tabela.rows[0].cells]
            cabecalho = [celula.text.strip() for celula in tabela.rows[1].cells]

            for coluna, tamanho in enumerate(cabecalho):
                with self.subTest(tamanho=tamanho):
                    self.assertIn(tamanho, ft.TAMANHOS_GRADE)
                    esperado = (
                        self.ROTULO_NUMERICO if tamanho.isdigit() else self.ROTULO_COMERCIAL
                    )
                    self.assertTrue(
                        rotulos[coluna].startswith(esperado),
                        f"O tamanho {tamanho} está sob o rótulo {rotulos[coluna]!r}, "
                        f"mas pertence ao grupo {esperado!r}.",
                    )

    def test_marcas_ficam_na_linha_abaixo_do_cabecalho(self):
        # A linha de rótulos foi inserida no topo; se ela acabar no lugar errado, as marcações de
        # tamanho deixam de ficar sob os nomes e a ficha impressa fica ilegível.
        for tabela in self._tabelas_da_grade():
            for coluna, celula in enumerate(tabela.rows[1].cells):
                tamanho = celula.text.strip()
                with self.subTest(tamanho=tamanho):
                    self.assertEqual(
                        tabela.rows[2].cells[coluna].text.strip(),
                        "{{ grade['" + tamanho + "'] }}",
                    )

    def test_os_dois_grupos_aparecem_rotulados(self):
        rotulos = {
            celula.text.strip()
            for tabela in self._tabelas_da_grade()
            for celula in tabela.rows[0].cells
        }
        self.assertTrue(any(r.startswith(self.ROTULO_COMERCIAL) for r in rotulos))
        self.assertTrue(any(r.startswith(self.ROTULO_NUMERICO) for r in rotulos))


class TestDetectorDeRunSplitting(unittest.TestCase):
    """Prova que o detector de fato dispara.

    Um detector que nunca acusa nada é indistinguível de um detector quebrado -- e como o template
    de produção está (corretamente) íntegro, todos os outros testes deste arquivo passariam mesmo
    se `_detectar_quebrados` tivesse um bug e sempre devolvesse lista vazia. Aqui a gente fabrica
    exatamente o estrago que o Word faz (partir o texto de uma célula em dois runs no meio de um
    placeholder) e confirma que a inspeção acusa."""

    def setUp(self):
        self.diretorio = tempfile.mkdtemp()
        self.caminho = os.path.join(self.diretorio, "quebrado.docx")
        shutil.copy(ft.CAMINHO_TEMPLATE, self.caminho)

    def tearDown(self):
        shutil.rmtree(self.diretorio, ignore_errors=True)

    def _quebrar_primeiro_placeholder(self) -> str:
        """Divide o run que contém `{{ ref }}` em dois, no meio do placeholder -- é o que o Word
        produz ao reeditar a célula."""
        doc = Document(self.caminho)
        for tabela in doc.tables:
            for linha in tabela.rows:
                for celula in linha.cells:
                    for paragrafo in celula.paragraphs:
                        for indice in range(len(paragrafo.runs)):
                            run = paragrafo.runs[indice]
                            texto = run.text or ""
                            if "{{" not in texto:
                                continue

                            meio = texto.index("{{") + 3  # cai dentro do "{{ x"
                            novo_elemento = copy.deepcopy(run._r)
                            run._r.addnext(novo_elemento)
                            run.text = texto[:meio]
                            paragrafo.runs[indice + 1].text = texto[meio:]

                            doc.save(self.caminho)
                            return texto
        self.fail("Nenhum placeholder encontrado no template para quebrar.")

    def test_detecta_placeholder_fatiado_entre_runs(self):
        original = self._quebrar_primeiro_placeholder()
        inspecao = ft.inspecionar_template(self.caminho)
        self.assertTrue(
            inspecao["quebrados"],
            f"O detector não acusou o placeholder {original!r} fatiado em dois runs.",
        )

    def test_template_intacto_nao_gera_falso_positivo(self):
        inspecao = ft.inspecionar_template(self.caminho)  # cópia ainda intacta
        self.assertEqual(inspecao["quebrados"], [])


class TestEstruturaDasTabelasDinamicas(unittest.TestCase):
    """Cada tabela dinâmica precisa do trio abre-laço / linha-modelo / fecha-laço.

    O `{%tr %}` do docxtpl **consome a linha inteira** onde aparece, substituindo-a pela instrução
    Jinja -- ele não marca "repita esta linha". Colocar `for` e `endfor` na mesma linha (o erro
    intuitivo) faz o regex guloso do docxtpl casar só com o último, e a renderização morre com
    "Encountered unknown tag 'endfor'".
    """

    @classmethod
    def setUpClass(cls):
        cls.inspecao = ft.inspecionar_template()

    def test_cada_lista_tem_for_e_endfor(self):
        placeholders = self.inspecao["placeholders"]
        aberturas = [p for p in placeholders if "tr for" in p]
        fechamentos = [p for p in placeholders if "tr endfor" in p]
        self.assertEqual(
            len(aberturas), len(ft.PLACEHOLDERS_LISTA),
            f"Esperava uma abertura de laço por lista dinâmica; achei {aberturas}",
        )
        self.assertEqual(len(fechamentos), len(aberturas), "Laço aberto sem fechar (ou vice-versa).")

    def test_for_e_endfor_nunca_na_mesma_linha(self):
        # Reconstrói a localização de cada tag para garantir que abertura e fechamento estão em
        # linhas diferentes da tabela -- a regra que o docxtpl impõe e não documenta bem.
        from docx import Document

        doc = Document(ft.CAMINHO_TEMPLATE)
        for indice_tabela, tabela in enumerate(doc.tables):
            for indice_linha, linha in enumerate(tabela.rows):
                texto_linha = " ".join(celula.text for celula in linha.cells)
                with self.subTest(tabela=indice_tabela, linha=indice_linha):
                    self.assertFalse(
                        "tr for" in texto_linha and "tr endfor" in texto_linha,
                        "Abertura e fechamento de laço na mesma linha -- o docxtpl vai casar só "
                        "com o último e a renderização falha.",
                    )


if __name__ == "__main__":
    unittest.main()
