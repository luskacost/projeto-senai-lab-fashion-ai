# -*- coding: utf-8 -*-
"""Testes do modelo de dados da ficha técnica (Fase 11, Task 1).

O valor destes testes está em pegar, no CI, dois tipos de erro que de outro modo só apareceriam
tarde e caros:

1. **Schema inválido para Structured Outputs.** A OpenAI rejeita com 400 qualquer objeto em modo
   `strict` que não tenha `additionalProperties: false` ou que não liste *todas* as propriedades
   em `required`. Sem estes testes, o erro só apareceria numa chamada real de API -- que custa
   crédito e que, por decisão do usuário, só rodamos com autorização explícita.

2. **Caminho de campo com erro de digitação em CAMPOS_NAO_INFERIVEIS.** Essa tupla é a trava de
   não-invenção que a Task 4 vai consumir. Um caminho escrito errado ("custos.preco" em vez de
   "custos.preco_total") não quebra nada visivelmente: simplesmente deixa de proteger o campo, e
   um preço inventado pela IA passa direto para a ficha. O teste amarra a tupla ao schema real.
"""

import unittest

import fichas_modelo as fm


def _objetos_do_schema(no, caminho="raiz"):
    """Percorre o schema e produz (caminho, objeto) para cada subschema do tipo object."""
    if not isinstance(no, dict):
        return

    tipo = no.get("type")
    if tipo == "object":
        yield caminho, no
        for nome, sub in no.get("properties", {}).items():
            yield from _objetos_do_schema(sub, f"{caminho}.{nome}")
    elif tipo == "array":
        yield from _objetos_do_schema(no.get("items", {}), f"{caminho}[]")


def _resolver_caminho(caminho: str):
    """Resolve um caminho como "aviamentos[].preco" dentro de SCHEMA_EXTRACAO.

    Retorna o subschema do campo, ou None se o caminho não existir.
    """
    no = fm.SCHEMA_EXTRACAO
    for parte in caminho.split("."):
        lista = parte.endswith("[]")
        nome = parte[:-2] if lista else parte

        propriedades = no.get("properties", {})
        if nome not in propriedades:
            return None
        no = propriedades[nome]

        if lista:
            if no.get("type") != "array":
                return None
            no = no.get("items", {})
    return no


class TestConformidadeStrictMode(unittest.TestCase):
    """Regras que a OpenAI impõe a todo schema usado com Structured Outputs em modo strict."""

    def test_todo_objeto_proibe_propriedades_extras(self):
        for caminho, obj in _objetos_do_schema(fm.SCHEMA_EXTRACAO):
            self.assertIs(
                obj.get("additionalProperties"), False,
                f"objeto em '{caminho}' precisa de additionalProperties: False",
            )

    def test_todo_objeto_exige_todas_as_propriedades(self):
        for caminho, obj in _objetos_do_schema(fm.SCHEMA_EXTRACAO):
            self.assertEqual(
                sorted(obj.get("required", [])), sorted(obj.get("properties", {}).keys()),
                f"objeto em '{caminho}': strict mode exige toda propriedade em required",
            )

    def test_nao_usa_palavras_chave_rejeitadas_pelo_strict_mode(self):
        # minItems/maxItems/pattern etc. não são suportados e fazem a API devolver 400.
        proibidas = {"minItems", "maxItems", "minLength", "maxLength", "pattern", "format",
                     "minimum", "maximum", "default", "oneOf", "allOf", "not"}

        def varrer(no, caminho):
            if isinstance(no, dict):
                for chave in no:
                    self.assertNotIn(chave, proibidas, f"'{chave}' não é suportado em strict mode (em {caminho})")
                for chave, sub in no.items():
                    varrer(sub, f"{caminho}.{chave}")
            elif isinstance(no, list):
                for item in no:
                    varrer(item, caminho)

        varrer(fm.SCHEMA_EXTRACAO, "raiz")

    def test_ausencia_de_numero_e_uniao_com_null(self):
        # Campo numérico não pode virar "" quando não há informação: o decodificador rejeitaria.
        preco = _resolver_caminho("custos.preco_total.custo")
        self.assertEqual(preco["properties"]["valor"]["type"], ["number", "null"])


class TestProveniencia(unittest.TestCase):
    """Todo campo de valor tem que carregar de onde o dado veio -- é o que torna a regra de
    não-invenção verificável por código em vez de confiável por prompt."""

    def test_todo_campo_folha_tem_valor_origem_e_trecho(self):
        for caminho, obj in _objetos_do_schema(fm.SCHEMA_EXTRACAO):
            propriedades = set(obj.get("properties", {}).keys())
            # Um campo folha é justamente o objeto que tem "valor"; os demais são agrupadores.
            if "valor" in propriedades:
                self.assertEqual(
                    propriedades, {"valor", "origem", "trecho"},
                    f"campo '{caminho}' tem formato de proveniência inesperado",
                )

    def test_origem_e_enum_fechado(self):
        campo = _resolver_caminho("ficha.ref")
        self.assertEqual(campo["properties"]["origem"]["enum"], list(fm.ORIGENS))

    def test_campos_nao_inferiveis_existem_no_schema(self):
        for caminho in fm.CAMPOS_NAO_INFERIVEIS:
            with self.subTest(campo=caminho):
                campo = _resolver_caminho(caminho)
                self.assertIsNotNone(campo, f"'{caminho}' não existe no schema -- caminho errado?")
                self.assertIn("valor", campo.get("properties", {}),
                              f"'{caminho}' não aponta para um campo de valor")

    def test_campos_criticos_estao_protegidos(self):
        # Guarda contra alguém remover uma proteção sem perceber o efeito: preço e composição
        # inventados viram pedido de compra e lote de tecido errados.
        for obrigatorio in ("aviamentos[].preco", "tecidos[].composicao", "custos.preco_total.custo",
                            "modelagem.numero_moldes"):
            self.assertIn(obrigatorio, fm.CAMPOS_NAO_INFERIVEIS)


class TestValoresVazios(unittest.TestCase):
    """ficha_vazia() é o ponto de partida de toda ficha nova e o fallback quando a extração
    falha -- se ela divergir do schema, o formulário do frontend quebra em campo indefinido."""

    def test_dados_vazios_tem_a_mesma_forma_do_schema(self):
        def comparar(schema, dados, caminho):
            tipo = schema.get("type")
            if tipo == "object":
                esperadas = set(schema.get("properties", {}).keys())
                if caminho == "raiz":
                    # Fase 14, Bloco M: "medidas" existe em dados mas NÃO no schema, de propósito
                    # -- tabela de medidas é onde um LLM mais inventa número plausível, então nem
                    # é oferecida à extração. A exceção é nomeada em fm.CHAVES_NAO_EXTRAIDAS, não
                    # um "set() diferente" solto aqui.
                    esperadas |= set(fm.CHAVES_NAO_EXTRAIDAS)
                self.assertIsInstance(dados, dict, f"esperava dict em '{caminho}'")
                self.assertEqual(set(dados.keys()), esperadas, f"chaves divergentes em '{caminho}'")
                for nome, sub in schema["properties"].items():
                    comparar(sub, dados[nome], f"{caminho}.{nome}")
            elif tipo == "array":
                self.assertIsInstance(dados, list, f"esperava lista em '{caminho}'")

        comparar(fm.SCHEMA_EXTRACAO, fm.dados_vazios(), "raiz")

    def test_chaves_nao_extraidas_estao_em_dados_mas_fora_do_schema(self):
        dados = fm.dados_vazios()
        for chave in fm.CHAVES_NAO_EXTRAIDAS:
            with self.subTest(chave=chave):
                self.assertIn(chave, dados)
                self.assertNotIn(chave, fm.SCHEMA_EXTRACAO["properties"])

    def test_campos_vazios_nascem_como_desconhecido(self):
        dados = fm.dados_vazios()
        self.assertEqual(dados["ficha"]["ref"]["origem"], fm.ORIGEM_DESCONHECIDO)
        self.assertEqual(dados["ficha"]["ref"]["valor"], "")
        self.assertIsNone(dados["custos"]["preco_total"]["custo"]["valor"])
        self.assertEqual(dados["ficha"]["ref"]["trecho"], "")

    def test_listas_dinamicas_comecam_vazias(self):
        dados = fm.dados_vazios()
        self.assertEqual(dados["aviamentos"], [])
        self.assertEqual(dados["tecidos"], [])
        self.assertEqual(dados["sequencia_operacional"], [])

    def test_ficha_vazia_e_pura(self):
        # Sem uuid/datetime aqui: o repositório (Task 5) preenche. Duas chamadas seguidas têm que
        # ser idênticas, senão este módulo deixa de ser determinístico e testável.
        self.assertEqual(fm.ficha_vazia(), fm.ficha_vazia())
        self.assertEqual(fm.ficha_vazia()["id"], "")
        self.assertEqual(fm.ficha_vazia()["status"], fm.STATUS_RASCUNHO)

    def test_ficha_vazia_nao_tem_desenho_aprovado(self):
        desenho = fm.ficha_vazia()["desenho"]
        self.assertFalse(desenho["solicitado"])
        self.assertEqual(desenho["versoes"], [])
        self.assertIsNone(desenho["versao_aprovada"])

    def test_ficha_vazia_precificacao_nasce_zerada_e_fora_de_dados(self):
        # Fase 14, Bloco P, Task 19: "precificacao" é irmã de "dados", não filha -- markup não
        # entra no SCHEMA_EXTRACAO (não é algo que um LLM deveria extrair do texto do usuário).
        ficha = fm.ficha_vazia()
        self.assertNotIn("precificacao", ficha["dados"])
        self.assertEqual(ficha["precificacao"], {
            "imposto_percentual": 0.0,
            "comissao_percentual": 0.0,
            "margem_lucro_percentual": 0.0,
        })

    def test_itens_vazios_batem_com_o_schema_da_lista(self):
        pares = (
            ("aviamentos[]", fm.aviamento_vazio()),
            ("tecidos[]", fm.tecido_vazio()),
            ("sequencia_operacional[]", fm.operacao_vazia()),
            ("cores_beneficiamentos[]", fm.cor_beneficiamento_vazia()),
            ("modelagem.partes[]", fm.parte_modelagem_vazia()),
        )
        for caminho, item in pares:
            with self.subTest(item=caminho):
                schema = _resolver_caminho(caminho)
                self.assertEqual(set(item.keys()), set(schema["properties"].keys()))

    def test_custo_vazio_bate_com_o_schema(self):
        schema = _resolver_caminho("custos.preco_total")
        self.assertEqual(set(fm.custo_vazio().keys()), set(schema["properties"].keys()))


class TestAcessoACampos(unittest.TestCase):
    """valor_de/origem_de são usados por validadores e pelo render do .docx, que recebem dados
    vindos de arquivo em disco -- possivelmente salvos por uma versão anterior do formato."""

    def test_valor_de_campo_normal(self):
        self.assertEqual(fm.valor_de({"valor": "CM-001", "origem": fm.ORIGEM_FORNECIDO, "trecho": "x"}), "CM-001")

    def test_valor_de_tolera_malformado(self):
        self.assertIsNone(fm.valor_de(None))
        self.assertIsNone(fm.valor_de("string solta"))
        self.assertIsNone(fm.valor_de({}))

    def test_origem_de_tolera_malformado_e_desconhecida(self):
        self.assertEqual(fm.origem_de(None), fm.ORIGEM_DESCONHECIDO)
        self.assertEqual(fm.origem_de({"valor": "x"}), fm.ORIGEM_DESCONHECIDO)
        self.assertEqual(fm.origem_de({"origem": "INVENTADA"}), fm.ORIGEM_DESCONHECIDO)

    def test_origem_de_campo_valido(self):
        self.assertEqual(fm.origem_de({"origem": fm.ORIGEM_FORNECIDO}), fm.ORIGEM_FORNECIDO)


class TestEstruturaConformeTemplateReal(unittest.TestCase):
    """Schema confirmado célula por célula contra templates/ficha_tecnica_v1.docx (recebido e
    inspecionado em 2026-09-11, via python-docx, não a partir da descrição textual do prompt nem
    do PDF de referência enviado antes -- os dois divergiam do documento oficial em vários
    pontos). Esses testes existem pra nunca mais deixar essas divergências voltarem
    silenciosamente."""

    def test_ficha_tem_tecnica_e_empresa_no_mesmo_bloco(self):
        # A tabela real "IDENTIFICAÇÃO DO PRODUTO" tem nome/colecao/descricao/designer/tecnica/
        # empresa/ref/data juntos -- ao contrário do que o PDF de referência sugeria, não existe
        # um bloco "BENEFICIAMENTOS" com nome/técnica/empresa separado do designer.
        ficha = _resolver_caminho("ficha")
        self.assertEqual(
            set(ficha["properties"].keys()),
            {"ref", "nome", "colecao", "descricao", "designer", "tecnica", "empresa", "data"},
        )

    def test_cores_beneficiamentos_e_tabela_dinamica_de_5_colunas(self):
        # A seção "CORES / BENEFICIAMENTOS" do .docx é UMA tabela (ITEM | DESCRIÇÃO | COR |
        # BENEFICIAMENTO | OBSERVAÇÕES), não duas coisas separadas (lista de cores + contato).
        item = _resolver_caminho("cores_beneficiamentos[]")
        self.assertEqual(
            set(item["properties"].keys()),
            {"item", "descricao", "cor", "beneficiamento", "observacoes"},
        )

    def test_custos_tem_outros_e_observacao_por_categoria(self):
        # A tabela CUSTOS real tem 5 categorias (não 4 -- "outros" só apareceu no .docx) e uma
        # linha "OBS.:" própria embaixo de cada uma.
        for categoria in ("aviamentos", "tecidos", "costura_beneficiamento", "outros", "preco_total"):
            with self.subTest(categoria=categoria):
                campo = _resolver_caminho(f"custos.{categoria}")
                self.assertEqual(set(campo["properties"].keys()), {"custo", "observacao"})

    def test_modelagem_modelista_e_moldes_sao_unicos_partes_e_lista(self):
        # A tabela MODELAGEM real tem MODELISTA/QUANTIDADE DE MOLDES (únicos) e PARTES/
        # COMPONENTES + OBSERVAÇÕES variando linha a linha -- e não tem campo "CORTE" (o .docx
        # real substituiu por "OBSERVAÇÕES", confirmado com o usuário).
        modelagem = _resolver_caminho("modelagem")
        self.assertEqual(set(modelagem["properties"].keys()), {"modelista", "numero_moldes", "partes"})
        self.assertNotIn("corte", modelagem["properties"])
        parte = _resolver_caminho("modelagem.partes[]")
        self.assertEqual(set(parte["properties"].keys()), {"descricao", "observacoes"})

    def test_dados_vazios_reflete_a_estrutura_real(self):
        dados = fm.dados_vazios()
        self.assertIn("tecnica", dados["ficha"])
        self.assertIn("empresa", dados["ficha"])
        self.assertNotIn("beneficiamento", dados)
        self.assertEqual(dados["cores_beneficiamentos"], [])
        self.assertEqual(set(dados["custos"].keys()), {"aviamentos", "tecidos", "costura_beneficiamento", "outros", "preco_total"})
        self.assertEqual(dados["modelagem"]["partes"], [])


class TestConstantes(unittest.TestCase):

    def test_grade_cobre_os_tamanhos_pedidos(self):
        self.assertEqual(fm.TAMANHOS_NUMERICOS[0], "34")
        self.assertEqual(fm.TAMANHOS_NUMERICOS[-1], "56")
        self.assertEqual(len(fm.TAMANHOS_NUMERICOS), 12)
        self.assertEqual(fm.TAMANHOS_COMERCIAIS, ("PP", "P", "M", "G", "GG", "XG"))

    def test_grade_do_schema_usa_as_constantes(self):
        numericos = _resolver_caminho("grade.numericos")
        self.assertEqual(numericos["properties"]["valor"]["items"]["enum"], list(fm.TAMANHOS_NUMERICOS))

    def test_status_rascunho_e_o_inicial(self):
        self.assertEqual(fm.STATUS_FICHA[0], fm.STATUS_RASCUNHO)


def _grade(numericos=(), comerciais=()):
    return {
        "grade": {
            "numericos": {"valor": list(numericos), "origem": fm.ORIGEM_FORNECIDO, "trecho": ""},
            "comerciais": {"valor": list(comerciais), "origem": fm.ORIGEM_FORNECIDO, "trecho": ""},
        }
    }


class TestTamanhosDaGrade(unittest.TestCase):
    """As colunas da tabela de medidas (Fase 14, Bloco M) saem daqui -- a ordem precisa ser
    canônica, não a ordem em que o usuário digitou, senão a checagem de progressão entre tamanhos
    vizinhos compararia pares errados."""

    def test_grade_vazia_nao_tem_tamanho(self):
        self.assertEqual(fm.tamanhos_da_grade(_grade()), [])
        self.assertEqual(fm.tamanhos_da_grade({}), [])

    def test_ordena_numericos_crescentes_independente_da_ordem_digitada(self):
        self.assertEqual(fm.tamanhos_da_grade(_grade(numericos=["42", "36", "40"])), ["36", "40", "42"])

    def test_ordena_comerciais_do_menor_para_o_maior(self):
        self.assertEqual(fm.tamanhos_da_grade(_grade(comerciais=["GG", "P", "M"])), ["P", "M", "GG"])

    def test_numericos_vem_antes_dos_comerciais(self):
        grade = _grade(numericos=["38"], comerciais=["M"])
        self.assertEqual(fm.tamanhos_da_grade(grade), ["38", "M"])

    def test_ignora_tamanho_fora_das_constantes(self):
        self.assertEqual(fm.tamanhos_da_grade(_grade(numericos=["38", "99"])), ["38"])


class TestLinhaMedidaVazia(unittest.TestCase):

    def test_cria_uma_celula_por_tamanho(self):
        linha = fm.linha_medida_vazia(["38", "40"])
        self.assertEqual(set(linha["valores"].keys()), {"38", "40"})
        self.assertIsNone(linha["valores"]["38"]["valor"])
        self.assertEqual(linha["valores"]["38"]["origem"], fm.ORIGEM_DESCONHECIDO)

    def test_sem_tamanhos_nasce_sem_celula(self):
        self.assertEqual(fm.linha_medida_vazia()["valores"], {})

    def test_ponto_nasce_vazio(self):
        self.assertEqual(fm.linha_medida_vazia(["38"])["ponto"]["valor"], "")


class TestGarantirChavesNaoExtraidas(unittest.TestCase):
    """A extração substitui `dados` inteiro pelo resultado da API (schema-shaped) -- sem isto, uma
    ficha criada por texto livre nasceria sem "medidas" e a tela quebraria nela."""

    def test_reintroduz_chave_ausente(self):
        dados = {"ficha": {}}
        fm.garantir_chaves_nao_extraidas(dados)
        self.assertEqual(dados["medidas"], [])

    def test_nao_sobrescreve_chave_ja_presente(self):
        dados = {"medidas": [{"ponto": fm.campo_texto_vazio(), "valores": {}}]}
        fm.garantir_chaves_nao_extraidas(dados)
        self.assertEqual(len(dados["medidas"]), 1)


if __name__ == "__main__":
    unittest.main()
