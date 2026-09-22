# -*- coding: utf-8 -*-
"""Testes de fichas_validacao.py (Fase 11, Task 2).

Todo teste aqui monta o dict de dados diretamente (sem passar por fichas_modelo.dados_vazios())
para deixar explícito, em cada caso, exatamente qual campo está sendo testado -- e para os
validadores continuarem corretos mesmo se alguém passar um dict incompleto/parcial, o que
acontece de verdade quando os dados vêm de um arquivo salvo por uma versão anterior do formato.
"""

import unittest

import fichas_modelo as fm
import fichas_validacao as fv


def _campo(valor, origem=fm.ORIGEM_FORNECIDO):
    return {"valor": valor, "origem": origem, "trecho": ""}


def _tecido(composicao=""):
    tecido = fm.tecido_vazio()
    tecido["composicao"] = _campo(composicao)
    return tecido


class TestExtrairPercentuais(unittest.TestCase):

    def test_extrai_percentuais_com_ponto_e_virgula(self):
        self.assertEqual(fv._extrair_percentuais("95% algodão, 5% elastano"), [95.0, 5.0])
        self.assertEqual(fv._extrair_percentuais("90,5% algodão e 9,5% elastano"), [90.5, 9.5])

    def test_texto_sem_percentual_retorna_vazio(self):
        self.assertEqual(fv._extrair_percentuais("algodão"), [])
        self.assertEqual(fv._extrair_percentuais(""), [])
        self.assertEqual(fv._extrair_percentuais(None), [])


class TestValidarComposicao(unittest.TestCase):

    def test_composicao_somando_100_nao_gera_alerta(self):
        dados = {"tecidos": [_tecido("95% algodão, 5% elastano")]}
        self.assertEqual(fv.validar_composicao(dados), [])

    def test_composicao_somando_menos_de_100_gera_alerta(self):
        dados = {"tecidos": [_tecido("60% algodão, 30% poliéster")]}
        alertas = fv.validar_composicao(dados)
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["codigo"], "composicao_nao_soma_100")
        self.assertEqual(alertas[0]["campo"], "tecidos[0].composicao")

    def test_composicao_somando_mais_de_100_gera_alerta(self):
        dados = {"tecidos": [_tecido("80% algodão, 30% elastano")]}
        self.assertEqual(len(fv.validar_composicao(dados)), 1)

    def test_dentro_da_tolerancia_nao_gera_alerta(self):
        dados = {"tecidos": [_tecido("98,5% algodão, 2% elastano")]}  # soma 100.5, tolerância 2pp
        self.assertEqual(fv.validar_composicao(dados), [])

    def test_sem_percentual_nao_gera_alerta(self):
        dados = {"tecidos": [_tecido("algodão")]}
        self.assertEqual(fv.validar_composicao(dados), [])

    def test_lista_vazia_de_tecidos_nao_gera_alerta(self):
        self.assertEqual(fv.validar_composicao({"tecidos": []}), [])
        self.assertEqual(fv.validar_composicao({}), [])

    def test_multiplos_tecidos_indice_correto_no_alerta(self):
        dados = {"tecidos": [_tecido("95% algodão, 5% elastano"), _tecido("50% algodão")]}
        alertas = fv.validar_composicao(dados)
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["campo"], "tecidos[1].composicao")


class TestValidarCustos(unittest.TestCase):

    def _custos(self, aviamentos, tecidos, costura, outros, total):
        def _cat(valor):
            return {"custo": _campo(valor), "observacao": _campo("")}
        return {"custos": {
            "aviamentos": _cat(aviamentos),
            "tecidos": _cat(tecidos),
            "costura_beneficiamento": _cat(costura),
            "outros": _cat(outros),
            "preco_total": _cat(total),
        }}

    def test_custos_batendo_nao_gera_alerta(self):
        dados = self._custos(10.0, 20.0, 5.0, 0.0, 35.0)
        self.assertEqual(fv.validar_custos(dados), [])

    def test_custos_batendo_com_outros_nao_gera_alerta(self):
        dados = self._custos(10.0, 20.0, 5.0, 8.0, 43.0)
        self.assertEqual(fv.validar_custos(dados), [])

    def test_custos_nao_batendo_gera_alerta(self):
        dados = self._custos(10.0, 20.0, 5.0, 0.0, 100.0)
        alertas = fv.validar_custos(dados)
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["codigo"], "custos_nao_batem")
        self.assertEqual(alertas[0]["campo"], "custos.preco_total.custo")

    def test_tolerancia_de_centavos_nao_gera_alerta(self):
        dados = self._custos(10.0, 20.0, 5.001, 0.0, 35.0)
        self.assertEqual(fv.validar_custos(dados), [])

    def test_algum_campo_ausente_nao_valida(self):
        # Regra 7 do prompt: sem dado suficiente, não inventa nem alerta -- "a definir" é legítimo.
        dados = self._custos(10.0, None, 5.0, 0.0, 35.0)
        self.assertEqual(fv.validar_custos(dados), [])

    def test_outros_ausente_nao_valida(self):
        dados = self._custos(10.0, 20.0, 5.0, None, 35.0)
        self.assertEqual(fv.validar_custos(dados), [])

    def test_todos_ausentes_nao_valida(self):
        dados = self._custos(None, None, None, None, None)
        self.assertEqual(fv.validar_custos(dados), [])

    def test_custos_ausentes_no_dict_nao_quebra(self):
        self.assertEqual(fv.validar_custos({}), [])


class TestValidarGrade(unittest.TestCase):

    def _grade(self, numericos, comerciais):
        return {"grade": {"numericos": _campo(numericos), "comerciais": _campo(comerciais)}}

    def test_grade_valida_nao_gera_alerta(self):
        dados = self._grade(["38", "40", "42"], ["M", "G"])
        self.assertEqual(fv.validar_grade(dados), [])

    def test_grade_vazia_gera_alerta(self):
        dados = self._grade([], [])
        alertas = fv.validar_grade(dados)
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["codigo"], "grade_vazia")

    def test_so_numerico_preenchido_nao_gera_alerta_de_vazia(self):
        dados = self._grade(["38", "40"], [])
        codigos = [a["codigo"] for a in fv.validar_grade(dados)]
        self.assertNotIn("grade_vazia", codigos)

    def test_tamanho_numerico_invalido_gera_alerta(self):
        dados = self._grade(["38", "39"], [])  # "39" não existe na grade numérica
        alertas = fv.validar_grade(dados)
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["codigo"], "tamanho_numerico_invalido")
        self.assertIn("39", alertas[0]["mensagem"])

    def test_tamanho_comercial_invalido_gera_alerta(self):
        dados = self._grade([], ["M", "XXG"])  # "XXG" não existe na grade comercial
        alertas = fv.validar_grade(dados)
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["codigo"], "tamanho_comercial_invalido")

    def test_grade_ausente_no_dict_nao_quebra(self):
        alertas = fv.validar_grade({})
        self.assertEqual([a["codigo"] for a in alertas], ["grade_vazia"])


class TestValidarCamposEssenciais(unittest.TestCase):

    def _ficha(self, ref="", nome="", descricao=""):
        return {"ficha": {"ref": _campo(ref), "nome": _campo(nome), "descricao": _campo(descricao)}}

    def test_todos_preenchidos_nao_gera_alerta(self):
        dados = self._ficha(ref="CM-001", nome="Camisa social", descricao="Camisa manga curta")
        self.assertEqual(fv.validar_campos_essenciais(dados), [])

    def test_todos_ausentes_gera_tres_alertas(self):
        dados = self._ficha()
        alertas = fv.validar_campos_essenciais(dados)
        self.assertEqual(len(alertas), 3)
        self.assertEqual({a["campo"] for a in alertas}, set(fv.CAMPOS_ESSENCIAIS))

    def test_apenas_um_ausente_gera_um_alerta(self):
        dados = self._ficha(ref="CM-001", nome="", descricao="Camisa manga curta")
        alertas = fv.validar_campos_essenciais(dados)
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["campo"], "ficha.nome")

    def test_ficha_ausente_no_dict_gera_todos_os_alertas(self):
        alertas = fv.validar_campos_essenciais({})
        self.assertEqual(len(alertas), 3)


class TestValidarFicha(unittest.TestCase):
    """O agregador que a Task 8 (tela de revisão) vai chamar."""

    def test_ficha_vazia_gera_essenciais_e_grade_vazia(self):
        dados = fm.dados_vazios()
        alertas = fv.validar_ficha(dados)
        codigos = [a["codigo"] for a in alertas]
        self.assertIn("campo_essencial_ausente", codigos)
        self.assertIn("grade_vazia", codigos)
        # sem tecido/custo nenhum, não deveria disparar os validadores desses -- e' o caso comum
        # de uma ficha recém-criada, não deve virar uma parede de alertas irrelevantes.
        self.assertNotIn("composicao_nao_soma_100", codigos)
        self.assertNotIn("custos_nao_batem", codigos)

    def test_ficha_completa_e_consistente_nao_gera_alerta(self):
        dados = fm.dados_vazios()
        dados["ficha"]["ref"] = _campo("CM-001")
        dados["ficha"]["nome"] = _campo("Camisa social")
        dados["ficha"]["descricao"] = _campo("Camisa social manga curta")
        dados["grade"]["numericos"] = _campo(["38", "40"])
        dados["tecidos"] = [_tecido("95% algodão, 5% elastano")]
        dados["custos"]["aviamentos"]["custo"] = _campo(10.0)
        dados["custos"]["tecidos"]["custo"] = _campo(20.0)
        dados["custos"]["costura_beneficiamento"]["custo"] = _campo(5.0)
        dados["custos"]["outros"]["custo"] = _campo(0.0)
        dados["custos"]["preco_total"]["custo"] = _campo(35.0)

        self.assertEqual(fv.validar_ficha(dados), [])

    def test_ordem_essenciais_antes_de_inconsistencias(self):
        dados = fm.dados_vazios()  # sem essenciais e sem grade
        alertas = fv.validar_ficha(dados)
        self.assertEqual(alertas[0]["codigo"], "campo_essencial_ausente")


def _dados_com_medidas(tamanhos_numericos=(), tamanhos_comerciais=(), linhas=()):
    dados = fm.dados_vazios()
    dados["grade"]["numericos"] = _campo(list(tamanhos_numericos))
    dados["grade"]["comerciais"] = _campo(list(tamanhos_comerciais))
    dados["medidas"] = list(linhas)
    return dados


def _linha_medida(ponto, valores):
    return {
        "ponto": _campo(ponto),
        "valores": {t: _campo(v) for t, v in valores.items()},
    }


def _codigos(alertas):
    return [a["codigo"] for a in alertas]


class TestValidarMedidas(unittest.TestCase):
    """Fase 14, Bloco M, Task 21 -- medida nunca vem da extração, então o que importa aqui é erro
    de digitação e dessincronia com a grade, não invenção da IA."""

    def test_sem_medidas_nao_gera_alerta(self):
        self.assertEqual(fv.validar_medidas(fm.dados_vazios()), [])
        self.assertEqual(fv.validar_medidas({}), [])

    def test_tabela_consistente_nao_gera_alerta(self):
        dados = _dados_com_medidas(
            tamanhos_numericos=["38", "40", "42"],
            linhas=[_linha_medida("Largura do ombro", {"38": 40.0, "40": 41.5, "42": 43.0})],
        )
        self.assertEqual(fv.validar_medidas(dados), [])

    def test_valor_igual_entre_tamanhos_vizinhos_e_aceito(self):
        # Progressão é "não decrescente", não "estritamente crescente": há ponto de medida que
        # legitimamente não muda entre dois tamanhos vizinhos.
        dados = _dados_com_medidas(
            tamanhos_numericos=["38", "40"],
            linhas=[_linha_medida("Comprimento da gola", {"38": 8.0, "40": 8.0})],
        )
        self.assertEqual(fv.validar_medidas(dados), [])

    def test_progressao_invertida_gera_alerta(self):
        dados = _dados_com_medidas(
            tamanhos_numericos=["38", "40"],
            linhas=[_linha_medida("Busto", {"38": 92.0, "40": 24.0})],  # 24 no lugar de 42
        )
        alertas = fv.validar_medidas(dados)
        self.assertIn("medida_nao_progressiva", _codigos(alertas))

    def test_progressao_nao_compara_numerico_com_comercial(self):
        # Grade mista: a fronteira 56 -> PP não é progressão real; comparar os dois acusaria erro
        # onde não há.
        dados = _dados_com_medidas(
            tamanhos_numericos=["56"],
            tamanhos_comerciais=["PP"],
            linhas=[_linha_medida("Busto", {"56": 120.0, "PP": 80.0})],
        )
        self.assertNotIn("medida_nao_progressiva", _codigos(fv.validar_medidas(dados)))

    def test_valor_zero_ou_negativo_gera_alerta(self):
        dados = _dados_com_medidas(
            tamanhos_numericos=["38", "40"],
            linhas=[_linha_medida("Busto", {"38": 0.0, "40": -5.0})],
        )
        alertas = fv.validar_medidas(dados)
        self.assertIn("medida_nao_positiva", _codigos(alertas))
        self.assertIn("38", alertas[0]["mensagem"])
        self.assertIn("40", alertas[0]["mensagem"])

    def test_tamanho_fora_da_grade_gera_alerta(self):
        dados = _dados_com_medidas(
            tamanhos_numericos=["38"],
            linhas=[_linha_medida("Busto", {"38": 92.0, "44": 98.0})],  # 44 saiu da grade
        )
        alertas = fv.validar_medidas(dados)
        self.assertIn("medida_fora_da_grade", _codigos(alertas))

    def test_celula_em_branco_gera_um_alerta_por_linha_nao_por_celula(self):
        dados = _dados_com_medidas(
            tamanhos_numericos=["38", "40", "42"],
            linhas=[_linha_medida("Busto", {"38": 92.0})],  # 40 e 42 em branco
        )
        alertas = [a for a in fv.validar_medidas(dados) if a["codigo"] == "medida_incompleta"]
        self.assertEqual(len(alertas), 1)
        self.assertIn("40", alertas[0]["mensagem"])
        self.assertIn("42", alertas[0]["mensagem"])

    def test_linha_totalmente_vazia_nao_gera_alerta_de_incompleta(self):
        # Rascunho com a linha só criada e ainda não preenchida -- alertar aqui seria ruído.
        dados = _dados_com_medidas(
            tamanhos_numericos=["38", "40"],
            linhas=[fm.linha_medida_vazia(["38", "40"])],
        )
        self.assertEqual(fv.validar_medidas(dados), [])

    def test_valores_sem_nome_do_ponto_gera_alerta(self):
        linha = _linha_medida("", {"38": 92.0})
        dados = _dados_com_medidas(tamanhos_numericos=["38"], linhas=[linha])
        self.assertIn("medida_sem_ponto", _codigos(fv.validar_medidas(dados)))

    def test_grade_acima_do_limite_de_colunas_do_documento(self):
        nove_tamanhos = ["34", "36", "38", "40", "42", "44", "46", "48", "50"]
        dados = _dados_com_medidas(
            tamanhos_numericos=nove_tamanhos,
            linhas=[_linha_medida("Busto", {t: 80.0 + i for i, t in enumerate(nove_tamanhos)})],
        )
        alertas = [a for a in fv.validar_medidas(dados) if a["codigo"] == "grade_excede_colunas_do_documento"]
        self.assertEqual(len(alertas), 1)
        self.assertIn("50", alertas[0]["mensagem"])  # o excedente é nomeado, não some calado

    def test_grade_no_limite_exato_nao_gera_alerta_de_colunas(self):
        oito = ["34", "36", "38", "40", "42", "44", "46", "48"]
        dados = _dados_com_medidas(
            tamanhos_numericos=oito,
            linhas=[_linha_medida("Busto", {t: 80.0 + i for i, t in enumerate(oito)})],
        )
        self.assertNotIn("grade_excede_colunas_do_documento", _codigos(fv.validar_medidas(dados)))

    def test_nunca_lanca_excecao_com_medidas_malformadas(self):
        for medidas in ("nao e uma lista", [None], ["nao e um dict"], [{"valores": "nao e um dict"}]):
            with self.subTest(medidas=medidas):
                dados = fm.dados_vazios()
                dados["medidas"] = medidas
                fv.validar_medidas(dados)  # não deve levantar

    def test_entra_no_validar_ficha(self):
        dados = _dados_com_medidas(
            tamanhos_numericos=["38", "40"],
            linhas=[_linha_medida("Busto", {"38": 92.0, "40": 24.0})],
        )
        self.assertIn("medida_nao_progressiva", _codigos(fv.validar_ficha(dados)))


if __name__ == "__main__":
    unittest.main()
