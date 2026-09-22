# -*- coding: utf-8 -*-
"""Testes de fichas_precificacao.py (Fase 14, Bloco P, Task 18).

Função pura -- todo teste monta o dict de `dados` diretamente, sem passar por
fichas_modelo.dados_vazios(), mesmo padrão de test_fichas_validacao.py.
"""

import unittest

import fichas_modelo as fm
import fichas_precificacao as fp


def _campo(valor, origem=fm.ORIGEM_FORNECIDO):
    return {"valor": valor, "origem": origem, "trecho": ""}


def _custo(valor):
    return {"custo": _campo(valor), "observacao": _campo("")}


def _dados_com_custos(aviamentos=None, tecidos=None, costura=None, outros=None):
    custos = {}
    if aviamentos is not None:
        custos["aviamentos"] = _custo(aviamentos)
    if tecidos is not None:
        custos["tecidos"] = _custo(tecidos)
    if costura is not None:
        custos["costura_beneficiamento"] = _custo(costura)
    if outros is not None:
        custos["outros"] = _custo(outros)
    return {"custos": custos}


class TestParametrosPadrao(unittest.TestCase):

    def test_todos_zerados(self):
        self.assertEqual(fp.parametros_padrao(), {
            "imposto_percentual": 0.0,
            "comissao_percentual": 0.0,
            "margem_lucro_percentual": 0.0,
        })


class TestCalcularSemParametros(unittest.TestCase):

    def test_sem_percentuais_preco_sugerido_igual_ao_custo(self):
        dados = _dados_com_custos(aviamentos=10, tecidos=50, costura=20, outros=5)
        resultado = fp.calcular(dados)
        self.assertTrue(resultado["calculavel"])
        self.assertEqual(resultado["custo_total"], 85.0)
        self.assertEqual(resultado["preco_sugerido"], 85.0)

    def test_parametros_none_equivale_a_todos_zerados(self):
        dados = _dados_com_custos(aviamentos=10, tecidos=50, costura=20, outros=5)
        self.assertEqual(fp.calcular(dados, None), fp.calcular(dados, {}))


class TestCalcularComPercentuais(unittest.TestCase):

    def test_markup_divisor_bate_com_a_conta_manual(self):
        # custo 100, 45% somados -> 100 / 0.55 = 181.818... -> 181.82
        dados = _dados_com_custos(aviamentos=100, tecidos=0, costura=0, outros=0)
        resultado = fp.calcular(dados, {
            "imposto_percentual": 10, "comissao_percentual": 15, "margem_lucro_percentual": 20,
        })
        self.assertTrue(resultado["calculavel"])
        self.assertEqual(resultado["preco_sugerido"], 181.82)
        self.assertEqual(resultado["percentual_total"], 45.0)
        self.assertAlmostEqual(resultado["divisor"], 0.55)

    def test_preco_sugerido_absorve_exatamente_os_percentuais_do_preco_de_venda(self):
        # Verifica a propriedade central do markup divisor: dos R$ 181,82, 45% saem em
        # imposto+comissao+margem e sobram os R$ 100 de custo -- é isso que o markup
        # multiplicador NÃO garante.
        dados = _dados_com_custos(aviamentos=100, tecidos=0, costura=0, outros=0)
        resultado = fp.calcular(dados, {
            "imposto_percentual": 10, "comissao_percentual": 15, "margem_lucro_percentual": 20,
        })
        preco = resultado["preco_sugerido"]
        sobra_apos_percentuais = preco * (1 - 0.45)
        self.assertAlmostEqual(sobra_apos_percentuais, 100.0, places=1)

    def test_parametro_como_string_numerica_funciona(self):
        dados = _dados_com_custos(aviamentos=100, tecidos=0, costura=0, outros=0)
        resultado = fp.calcular(dados, {"margem_lucro_percentual": "20"})
        self.assertTrue(resultado["calculavel"])
        self.assertEqual(resultado["preco_sugerido"], 125.0)  # 100 / 0.8


class TestCalcularCasosNaoCalculaveis(unittest.TestCase):

    def test_nenhum_custo_informado(self):
        resultado = fp.calcular({"custos": {}})
        self.assertFalse(resultado["calculavel"])
        self.assertIsNone(resultado["preco_sugerido"])
        self.assertIn("Nenhum custo", resultado["motivo"])

    def test_percentuais_somando_100_nao_calculavel(self):
        dados = _dados_com_custos(aviamentos=100)
        resultado = fp.calcular(dados, {"margem_lucro_percentual": 100})
        self.assertFalse(resultado["calculavel"])
        self.assertIsNone(resultado["preco_sugerido"])

    def test_percentuais_somando_mais_de_100_nao_calculavel(self):
        dados = _dados_com_custos(aviamentos=100)
        resultado = fp.calcular(dados, {
            "imposto_percentual": 60, "comissao_percentual": 60,
        })
        self.assertFalse(resultado["calculavel"])
        self.assertIn("100%", resultado["motivo"])

    def test_percentual_negativo_nao_calculavel(self):
        dados = _dados_com_custos(aviamentos=100)
        resultado = fp.calcular(dados, {"margem_lucro_percentual": -5})
        self.assertFalse(resultado["calculavel"])
        self.assertIn("negativo", resultado["motivo"])

    def test_percentual_nao_numerico_nao_calculavel(self):
        dados = _dados_com_custos(aviamentos=100)
        resultado = fp.calcular(dados, {"margem_lucro_percentual": "abacate"})
        self.assertFalse(resultado["calculavel"])
        self.assertIn("número válido", resultado["motivo"])

    def test_nunca_lanca_excecao_com_dados_vazios_ou_malformados(self):
        self.assertFalse(fp.calcular({})["calculavel"])
        self.assertFalse(fp.calcular(None)["calculavel"])
        self.assertFalse(fp.calcular({"custos": None})["calculavel"])
        self.assertFalse(fp.calcular({"custos": "nao e um dict"})["calculavel"])
        self.assertFalse(fp.calcular({"custos": {"aviamentos": "nao e um dict"}})["calculavel"])
        self.assertFalse(fp.calcular("nem um dict e")["calculavel"])
        self.assertFalse(fp.calcular({"custos": {"aviamentos": None}})["calculavel"])


class TestCategoriasInformadasEAusentes(unittest.TestCase):

    def test_categorias_parciais_aparecem_em_informadas_e_ausentes(self):
        dados = _dados_com_custos(aviamentos=10, tecidos=20)  # costura/outros ausentes
        resultado = fp.calcular(dados)
        self.assertTrue(resultado["calculavel"])
        self.assertEqual(resultado["categorias_informadas"], {"aviamentos": 10.0, "tecidos": 20.0})
        self.assertEqual(set(resultado["categorias_ausentes"]), {"costura_beneficiamento", "outros"})
        self.assertEqual(resultado["custo_total"], 30.0)

    def test_todas_as_4_categorias_informadas_nao_deixa_ausente(self):
        dados = _dados_com_custos(aviamentos=10, tecidos=20, costura=5, outros=1)
        resultado = fp.calcular(dados)
        self.assertEqual(resultado["categorias_ausentes"], [])


class TestArredondamento(unittest.TestCase):

    def test_arredonda_meio_para_cima(self):
        # 10 / (1 - 33/100) = 10 / 0.67 = 14.9253731... -> 14.93 (ROUND_HALF_UP)
        dados = _dados_com_custos(aviamentos=10)
        resultado = fp.calcular(dados, {"margem_lucro_percentual": 33})
        self.assertEqual(resultado["preco_sugerido"], 14.93)


if __name__ == "__main__":
    unittest.main()
