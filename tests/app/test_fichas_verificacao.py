# -*- coding: utf-8 -*-
"""Testes de fichas_verificacao.py (Fase 11, Task 4).

Esta é a suíte mais importante da Fase 11 até aqui: ela prova que a regra de não-invenção do
produto ("a IA nunca pode inventar preço, fornecedor, composição, medida, número de moldes...")
é uma garantia mecânica, e não uma esperança de que o prompt da Task 3 foi obedecido. Os testes
da classe TestCenariosAdversariais simulam exatamente o caso que a garantia existe para pegar: um
modelo que devolve FORNECIDO/um trecho para um dado que ele mesmo inventou.
"""

import unittest

import fichas_modelo as fm
import fichas_verificacao as fv


def _campo(valor, origem=fm.ORIGEM_FORNECIDO, trecho=""):
    return {"valor": valor, "origem": origem, "trecho": trecho}


class TestNormalizacao(unittest.TestCase):

    def test_remove_acento_acentos_e_caixa(self):
        self.assertEqual(fv._normalizar("ALGODÃO"), fv._normalizar("algodao"))
        self.assertEqual(fv._normalizar("Coração"), "coracao")

    def test_colapsa_espacos(self):
        self.assertEqual(fv._normalizar("camisa   preta"), fv._normalizar("camisa preta"))

    def test_tolera_none_e_nao_string(self):
        self.assertEqual(fv._normalizar(None), "")
        self.assertEqual(fv._normalizar(123), "")


class TestPercorrerCampos(unittest.TestCase):

    def test_encontra_campo_simples(self):
        dados = {"ficha": {"ref": _campo("CM-001")}}
        resultado = dict(fv._percorrer_campos(dados, ""))
        self.assertIn("ficha.ref", resultado)
        self.assertEqual(resultado["ficha.ref"]["valor"], "CM-001")

    def test_encontra_campo_dentro_de_lista(self):
        dados = {"aviamentos": [{"preco": _campo(5.0)}]}
        resultado = dict(fv._percorrer_campos(dados, ""))
        self.assertIn("aviamentos[].preco", resultado)

    def test_nao_confunde_objeto_agrupador_com_campo_folha(self):
        # custos.aviamentos = {"custo": {...}, "observacao": {...}} tem uma chave chamada "custo"
        # mas NÃO é ele mesmo um campo de proveniência (não tem exatamente valor/origem/trecho).
        dados = {"custos": {"aviamentos": {"custo": _campo(10.0), "observacao": _campo("")}}}
        resultado = dict(fv._percorrer_campos(dados, ""))
        self.assertIn("custos.aviamentos.custo", resultado)
        self.assertNotIn("custos.aviamentos", resultado)


class TestVerificacaoDeOrigem(unittest.TestCase):
    """Um campo FORNECIDO cujo trecho não bate com o texto real é rebaixado para INFERIDO --
    independente de o campo ser crítico ou não."""

    def test_trecho_presente_no_texto_mantem_fornecido(self):
        dados = {"ficha": {"nome": _campo("Camisa Social", trecho="camisa social")}}
        corrigidos, alertas = fv.verificar_proveniencia(dados, "Quero uma Camisa Social branca.")
        self.assertEqual(corrigidos["ficha"]["nome"]["origem"], fm.ORIGEM_FORNECIDO)
        self.assertEqual(alertas, [])

    def test_trecho_tolera_acento_e_caixa_diferentes(self):
        dados = {"ficha": {"descricao": _campo("100% algodão", trecho="100% ALGODAO")}}
        corrigidos, _ = fv.verificar_proveniencia(dados, "a camisa é feita de 100% algodão puro")
        self.assertEqual(corrigidos["ficha"]["descricao"]["origem"], fm.ORIGEM_FORNECIDO)

    def test_trecho_ausente_do_texto_rebaixa_para_inferido(self):
        dados = {"ficha": {"colecao": _campo("Verão 2027", trecho="coleção verão 2027")}}
        corrigidos, alertas = fv.verificar_proveniencia(dados, "quero uma camisa preta")
        self.assertEqual(corrigidos["ficha"]["colecao"]["origem"], fm.ORIGEM_INFERIDO)
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["codigo"], "origem_rebaixada")
        self.assertEqual(alertas[0]["campo"], "ficha.colecao")

    def test_trecho_vazio_com_origem_fornecido_rebaixa(self):
        # "" é substring de qualquer string em Python -- a checagem precisa recusar isso
        # explicitamente, senão um trecho vazio passaria como "válido" por acidente.
        dados = {"ficha": {"nome": _campo("Camisa", trecho="")}}
        corrigidos, alertas = fv.verificar_proveniencia(dados, "quero uma camisa qualquer")
        self.assertEqual(corrigidos["ficha"]["nome"]["origem"], fm.ORIGEM_INFERIDO)
        self.assertEqual(len(alertas), 1)

    def test_origem_inferido_nao_e_verificada_contra_o_texto(self):
        # Só FORNECIDO passa pela checagem de honestidade -- INFERIDO já se declara como palpite.
        dados = {"ficha": {"designer": _campo("Ana", origem=fm.ORIGEM_INFERIDO, trecho="não existe no texto")}}
        corrigidos, alertas = fv.verificar_proveniencia(dados, "texto qualquer sem relação")
        # ficha.designer é campo crítico -- o alerta esperado aqui é o de zerar, não o de rebaixar.
        codigos = [a["codigo"] for a in alertas]
        self.assertNotIn("origem_rebaixada", codigos)


class TestValorVazioComo(unittest.TestCase):
    """Regressão: zerar um campo numérico que já está None caía no fallback de texto (""),
    trocando silenciosamente um número ausente por string vazia -- e quebrando qualquer soma
    feita depois em fichas_validacao.validar_custos() com dados totalmente vazios (o caso mais
    comum de todos: uma ficha recém-criada, ainda sem nenhum custo preenchido)."""

    def test_none_permanece_none(self):
        self.assertIsNone(fv._valor_vazio_como(None))

    def test_numero_vira_none(self):
        self.assertIsNone(fv._valor_vazio_como(42.0))
        self.assertIsNone(fv._valor_vazio_como(42))

    def test_lista_vira_lista_vazia(self):
        self.assertEqual(fv._valor_vazio_como(["34", "36"]), [])

    def test_texto_vira_string_vazia(self):
        self.assertEqual(fv._valor_vazio_como("algo"), "")

    def test_ficha_vazia_nao_quebra_verificacao(self):
        # dados_vazios() inteiro, sem nenhum campo tocado -- todo campo crítico já nasce
        # DESCONHECIDO e será "zerado" (um no-op, já que já está vazio); isso não pode lançar.
        corrigidos, _ = fv.verificar_proveniencia(fm.dados_vazios(), "texto qualquer")
        self.assertIsNone(corrigidos["custos"]["preco_total"]["custo"]["valor"])


class TestAllowlistDeCamposCriticos(unittest.TestCase):
    """Depois da verificação de honestidade, todo campo em CAMPOS_NAO_INFERIVEIS que não for
    FORNECIDO é zerado -- não importa se a origem é INFERIDO ou DESCONHECIDO."""

    def test_campo_critico_fornecido_e_verificado_sobrevive(self):
        dados = {"tecidos": [{"preco": _campo(45.0, trecho="R$ 45 o metro")}]}
        corrigidos, alertas = fv.verificar_proveniencia(dados, "o tecido custa R$ 45 o metro")
        self.assertEqual(corrigidos["tecidos"][0]["preco"]["valor"], 45.0)
        self.assertEqual(alertas, [])

    def test_campo_critico_inferido_e_zerado(self):
        dados = {"tecidos": [{"preco": _campo(45.0, origem=fm.ORIGEM_INFERIDO, trecho="")}]}
        corrigidos, alertas = fv.verificar_proveniencia(dados, "quero uma camisa de algodão")
        self.assertIsNone(corrigidos["tecidos"][0]["preco"]["valor"])
        self.assertEqual(corrigidos["tecidos"][0]["preco"]["origem"], fm.ORIGEM_DESCONHECIDO)
        self.assertEqual(corrigidos["tecidos"][0]["preco"]["trecho"], "")
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["codigo"], "campo_critico_zerado")

    def test_campo_critico_ja_desconhecido_nao_gera_alerta_redundante(self):
        # Zerar um campo que já está vazio não é novidade nenhuma -- não vale a pena um alerta.
        dados = {"tecidos": [{"preco": _campo(None, origem=fm.ORIGEM_DESCONHECIDO)}]}
        _, alertas = fv.verificar_proveniencia(dados, "quero uma camisa de algodão")
        self.assertEqual(alertas, [])

    def test_campo_nao_critico_inferido_nao_e_zerado(self):
        # "cor" não está em CAMPOS_NAO_INFERIVEIS -- pode ficar como inferido sem ser apagado.
        dados = {"tecidos": [{"cor": _campo("azul", origem=fm.ORIGEM_INFERIDO)}]}
        corrigidos, alertas = fv.verificar_proveniencia(dados, "quero uma camisa qualquer")
        self.assertEqual(corrigidos["tecidos"][0]["cor"]["valor"], "azul")
        self.assertEqual(alertas, [])

    def test_zera_todos_os_campos_criticos_do_schema(self):
        # Varre CAMPOS_NAO_INFERIVEIS inteiro contra uma ficha_vazia() onde todo campo critico
        # está (adversarialmente) marcado FORNECIDO com um trecho que não existe no texto real.
        dados = fm.dados_vazios()
        for caminho in fm.CAMPOS_NAO_INFERIVEIS:
            _definir_valor_adversarial(dados, caminho)

        corrigidos, alertas = fv.verificar_proveniencia(dados, "texto do usuário sem nenhum dado técnico real")

        for caminho in fm.CAMPOS_NAO_INFERIVEIS:
            with self.subTest(campo=caminho):
                campo = _ler_campo(corrigidos, caminho)
                self.assertIn(campo["valor"], (None, ""), f"'{caminho}' deveria ter sido zerado")
                self.assertEqual(campo["origem"], fm.ORIGEM_DESCONHECIDO)

        codigos_zerados = {a["campo"] for a in alertas if a["codigo"] == "campo_critico_zerado"}
        self.assertEqual(codigos_zerados, set(fm.CAMPOS_NAO_INFERIVEIS))


class TestCenariosAdversariais(unittest.TestCase):
    """Simula um modelo que blefa: marca FORNECIDO um dado que ele mesmo inventou, citando um
    trecho que não existe no texto do usuário (ou que existe mas não diz o que o campo afirma)."""

    def test_preco_inventado_com_trecho_fabricado_e_zerado(self):
        dados = fm.dados_vazios()
        dados["tecidos"] = [{
            **fm.tecido_vazio(),
            "preco": _campo(120.0, trecho="o tecido custa 120 reais o metro"),
        }]
        # O usuário nunca mencionou preço nenhum.
        corrigidos, alertas = fv.verificar_proveniencia(dados, "quero uma camisa de algodão preta")

        self.assertIsNone(corrigidos["tecidos"][0]["preco"]["valor"])
        codigos = [a["codigo"] for a in alertas]
        self.assertIn("origem_rebaixada", codigos)  # o trecho citado não existe no texto
        self.assertIn("campo_critico_zerado", codigos)  # e por isso o preço foi zerado

    def test_numero_de_moldes_inventado_e_zerado(self):
        dados = fm.dados_vazios()
        dados["modelagem"]["numero_moldes"] = _campo(12, trecho="12 moldes")
        corrigidos, alertas = fv.verificar_proveniencia(dados, "quero uma saia midi plissada")
        self.assertIsNone(corrigidos["modelagem"]["numero_moldes"]["valor"])
        self.assertTrue(any(a["campo"] == "modelagem.numero_moldes" for a in alertas))

    def test_fornecedor_com_trecho_que_existe_mas_nao_sustenta_o_campo(self):
        # Trecho existe no texto, mas fala de outra coisa -- o modelo citou algo real só pra
        # parecer embasado. A checagem por substring não pega esse caso sutil (limite conhecido
        # do método: verifica só se o trecho existe no texto, não se ele de fato sustenta o
        # campo) -- mas o campo continua protegido por ser crítico: se a origem sobreviver como
        # FORNECIDO de forma incorreta, ainda cabe ao usuário corrigir na revisão (Task 8).
        dados = fm.dados_vazios()
        dados["aviamentos"] = [{
            **fm.aviamento_vazio(),
            "fornecedor": _campo("Botões União Ltda", trecho="camisa de algodão"),
        }]
        corrigidos, _ = fv.verificar_proveniencia(dados, "quero uma camisa de algodão preta")
        # Trecho "camisa de algodão" EXISTE no texto -> não é rebaixado por honestidade, mas o
        # valor "Botões União Ltda" nunca foi dito -- demonstra o limite do método, documentado.
        self.assertEqual(corrigidos["aviamentos"][0]["fornecedor"]["origem"], fm.ORIGEM_FORNECIDO)

    def test_composicao_inventada_sem_trecho_e_zerada(self):
        dados = fm.dados_vazios()
        dados["tecidos"] = [{**fm.tecido_vazio(), "composicao": _campo("95% algodão, 5% elastano", trecho="")}]
        corrigidos, alertas = fv.verificar_proveniencia(dados, "quero uma camisa social")
        self.assertEqual(corrigidos["tecidos"][0]["composicao"]["valor"], "")
        self.assertTrue(any(a["campo"] == "tecidos[].composicao" for a in alertas))

    def test_ficha_legitima_sem_dados_criticos_nao_gera_alerta_nenhum(self):
        # Contraprova: texto que só menciona nome/descrição não deveria gerar NENHUM alerta --
        # os validadores não podem ser barulhentos a ponto de incomodar o caso comum e correto.
        dados = fm.dados_vazios()
        dados["ficha"]["nome"] = _campo("Camisa Social Branca", trecho="camisa social branca")
        dados["ficha"]["descricao"] = _campo("Camisa social de algodão", trecho="camisa social de algodão")
        texto = "Quero uma Camisa Social Branca. É uma camisa social de algodão."
        _, alertas = fv.verificar_proveniencia(dados, texto)
        self.assertEqual(alertas, [])


class TestNaoModificaEntrada(unittest.TestCase):

    def test_dict_original_nao_e_alterado(self):
        dados = fm.dados_vazios()
        dados["modelagem"]["numero_moldes"] = _campo(99, trecho="não está no texto")
        original_copia = fm.dados_vazios()
        original_copia["modelagem"]["numero_moldes"] = _campo(99, trecho="não está no texto")

        fv.verificar_proveniencia(dados, "texto qualquer")

        self.assertEqual(dados, original_copia)


def _definir_valor_adversarial(dados: dict, caminho: str) -> None:
    """Navega por um caminho estilo 'aviamentos[].preco' dentro de `dados` (populando listas
    vazias com um item quando necessário) e marca o campo final como FORNECIDO com um trecho que
    certamente não existe no texto de teste usado por TestAllowlistDeCamposCriticos."""
    partes = caminho.split(".")
    no = dados
    for i, parte in enumerate(partes):
        eh_lista = parte.endswith("[]")
        nome = parte[:-2] if eh_lista else parte
        ultimo = i == len(partes) - 1

        if eh_lista:
            if not no[nome]:
                no[nome].append({})
            no = no[nome][0]
        elif ultimo:
            no[nome] = _campo(_valor_de_exemplo(), trecho="trecho-fabricado-que-nao-existe-no-texto-de-teste")
        else:
            no = no[nome]


def _valor_de_exemplo():
    return "valor de teste"


def _ler_campo(dados: dict, caminho: str) -> dict:
    partes = caminho.split(".")
    no = dados
    for parte in partes:
        eh_lista = parte.endswith("[]")
        nome = parte[:-2] if eh_lista else parte
        no = no[nome]
        if eh_lista:
            no = no[0]
    return no


if __name__ == "__main__":
    unittest.main()
