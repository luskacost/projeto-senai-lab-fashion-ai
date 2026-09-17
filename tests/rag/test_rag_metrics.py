# -*- coding: utf-8 -*-
"""Testes das métricas de IR (Fase 13, Task 8).

Todos os valores esperados foram calculados à mão e estão demonstrados no próprio teste. Isso é
deliberado: uma métrica errada não quebra nada visivelmente -- ela produz um número plausível e
todas as decisões tomadas em cima dele ficam erradas em silêncio. Conferir contra a fórmula, e não
contra "o que a função devolveu quando eu rodei", é a única forma de pegar isso.
"""

import math
import unittest

import rag_metrics as m


class TestPrecision(unittest.TestCase):

    def test_precision_em_k_divide_por_k(self):
        # 2 relevantes entre os 3 primeiros, k=3 -> 2/3
        self.assertAlmostEqual(m.precision_em_k([True, False, True], k=3), 2 / 3)

    def test_precision_em_k_penaliza_quando_devolveu_menos_que_k(self):
        # Um único chunk, perfeito, com k=5: a métrica clássica dá 0,20 -- comportamento correto
        # da fórmula, e exatamente o motivo de existir precision_dos_recuperados ao lado.
        self.assertAlmostEqual(m.precision_em_k([True], k=5), 0.2)

    def test_precision_dos_recuperados_ignora_k(self):
        self.assertAlmostEqual(m.precision_dos_recuperados([True]), 1.0)
        self.assertAlmostEqual(m.precision_dos_recuperados([True, False, True]), 2 / 3)

    def test_precision_dos_recuperados_com_lista_vazia(self):
        # Não recuperar nada não é "100% de precisão"; é ausência de resultado.
        self.assertEqual(m.precision_dos_recuperados([]), 0.0)

    def test_precision_em_k_so_olha_os_k_primeiros(self):
        # O relevante está na posição 4, fora do corte k=2.
        self.assertAlmostEqual(m.precision_em_k([False, False, False, True], k=2), 0.0)


class TestRecall(unittest.TestCase):

    def test_recall_divide_pelo_total_do_corpus(self):
        # 2 relevantes recuperados, 4 existem no corpus -> 0,5
        self.assertAlmostEqual(m.recall_em_k([True, False, True], k=3, total_relevantes=4), 0.5)

    def test_recall_completo_quando_recupera_todos_os_que_existem(self):
        self.assertAlmostEqual(m.recall_em_k([True], k=5, total_relevantes=1), 1.0)

    def test_recall_ignora_relevantes_alem_do_corte_k(self):
        # O segundo relevante está na posição 3, fora de k=2: recall@2 = 1/2 dos 2 existentes.
        self.assertAlmostEqual(m.recall_em_k([True, False, True], k=2, total_relevantes=2), 0.5)

    def test_recall_sem_relevantes_no_corpus_levanta_erro(self):
        # Indefinido, não zero -- devolver 0.0 aqui faria um caso de abstenção parecer falha
        # gravíssima de recuperação.
        with self.assertRaises(ValueError):
            m.recall_em_k([False], k=5, total_relevantes=0)


class TestReciprocalRank(unittest.TestCase):

    def test_primeiro_relevante_na_primeira_posicao(self):
        self.assertAlmostEqual(m.reciprocal_rank([True, False]), 1.0)

    def test_primeiro_relevante_na_terceira_posicao(self):
        self.assertAlmostEqual(m.reciprocal_rank([False, False, True]), 1 / 3)

    def test_nenhum_relevante(self):
        self.assertEqual(m.reciprocal_rank([False, False]), 0.0)

    def test_lista_vazia(self):
        self.assertEqual(m.reciprocal_rank([]), 0.0)


class TestNdcg(unittest.TestCase):

    def test_ranking_ideal_da_um(self):
        # 2 relevantes no corpus, ambos nas duas primeiras posições = ranking perfeito.
        self.assertAlmostEqual(m.ndcg_em_k([True, True, False], k=3, total_relevantes=2), 1.0)

    def test_valor_calculado_a_mao(self):
        # relevancias=[True, False, True], k=3, total_relevantes=4
        #   DCG  = 1/log2(2) + 0 + 1/log2(4) = 1 + 0,5 = 1,5
        #   IDCG = 1/log2(2) + 1/log2(3) + 1/log2(4) = 1 + 0,63093 + 0,5 = 2,13093
        #   nDCG = 1,5 / 2,13093 = 0,70392
        dcg = 1.0 + 1.0 / math.log2(4)
        idcg = 1.0 + 1.0 / math.log2(3) + 1.0 / math.log2(4)
        self.assertAlmostEqual(
            m.ndcg_em_k([True, False, True], k=3, total_relevantes=4), dcg / idcg, places=6
        )
        self.assertAlmostEqual(m.ndcg_em_k([True, False, True], k=3, total_relevantes=4), 0.7039, places=4)

    def test_penaliza_relevante_mal_posicionado(self):
        # Mesmo conteúdo recuperado, posições diferentes: o topo vale mais.
        no_topo = m.ndcg_em_k([True, False, False], k=3, total_relevantes=1)
        no_fim = m.ndcg_em_k([False, False, True], k=3, total_relevantes=1)
        self.assertAlmostEqual(no_topo, 1.0)
        self.assertLess(no_fim, no_topo)
        self.assertAlmostEqual(no_fim, 1.0 / math.log2(4))  # 1/2 = 0,5

    def test_idcg_limita_se_existem_mais_relevantes_que_k(self):
        # 10 relevantes no corpus mas k=2: o ideal possível são 2, não 10.
        self.assertAlmostEqual(m.ndcg_em_k([True, True], k=2, total_relevantes=10), 1.0)

    def test_nenhum_relevante_recuperado(self):
        self.assertEqual(m.ndcg_em_k([False, False], k=2, total_relevantes=3), 0.0)

    def test_sem_relevantes_no_corpus_levanta_erro(self):
        with self.assertRaises(ValueError):
            m.ndcg_em_k([False], k=5, total_relevantes=0)


class TestMedia(unittest.TestCase):

    def test_media_simples(self):
        self.assertAlmostEqual(m.media([1.0, 0.0, 0.5]), 0.5)

    def test_media_de_lista_vazia_e_zero(self):
        self.assertEqual(m.media([]), 0.0)


if __name__ == "__main__":
    unittest.main()
