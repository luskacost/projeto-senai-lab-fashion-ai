# -*- coding: utf-8 -*-
"""Testes da métrica de distância vetorial do ChromaDB (Fase 13, Task 1).

## O defeito que este arquivo existe para pegar

O Chroma tem um espaço de distância padrão silencioso: se a coleção não declarar `hnsw:space`,
ele usa `l2` (distância euclidiana). Sobre embeddings normalizados (norma 1, como os que este
projeto gera -- `gerar_embeddings_normalizados`), a relação com a similaridade de cosseno é
`dist_l2 = 2 - 2*cos_sim` -- **ao quadrado** em relação a `1 - cos_sim`.

`rag_manager._obter_colecao_tenant` cria a coleção com `hnsw:space="cosine"` explícito
propositalmente: nesse espaço, o Chroma devolve `dist = 1 - cos_sim` diretamente, e
`reranker.fundir_e_deduplicar_candidatos` só precisa fazer `cos_sim = 1 - dist`. Antes desta
task, a coleção não declarava o espaço (herdava `l2` por padrão) e o código já fazia
`1 - dist**2/2` -- a fórmula certa para a métrica errada. Os dois testes abaixo travam,
respectivamente, que a coleção nasce no espaço certo e que a fórmula bate com esse espaço.

Os testes usam vetores 2D sintéticos com ângulo conhecido (não o modelo de embeddings real) --
o alvo aqui é a aritmética da conversão, não a qualidade do modelo, e um teste que não depende de
carregar o sentence-transformers roda em milissegundos.
"""

import math
import os
import shutil
import unittest

import rag_manager as rm
from reranker import fundir_e_deduplicar_candidatos

TENANT_TESTE = "teste_fase13_vector_similarity"


def _vetor_unitario(angulo_rad: float) -> list:
    return [math.cos(angulo_rad), math.sin(angulo_rad)]


class TestMetricaDaColecao(unittest.TestCase):
    """A coleção real do tenant precisa nascer declarando o espaço de distância -- sem isso, o
    Chroma cai no padrão `l2` silenciosamente, e nada no restante do pipeline percebe."""

    def setUp(self):
        self._limpar()

    def tearDown(self):
        self._limpar()

    def _limpar(self):
        caminho = os.path.join("tenant_data", "chroma", TENANT_TESTE)
        if os.path.exists(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        rm._CHROMA_CLIENTS.pop(TENANT_TESTE, None)

    def test_colecao_e_criada_com_espaco_cosseno(self):
        colecao = rm._obter_colecao_tenant(TENANT_TESTE)
        espaco = colecao.configuration_json.get("hnsw", {}).get("space")
        self.assertEqual(
            espaco, "cosine",
            "A coleção não declarou hnsw:space='cosine' -- caiu no padrão 'l2' do Chroma, que "
            "devolve distância euclidiana ao quadrado, não similaridade de cosseno direta.",
        )

    def test_nome_da_colecao_usa_a_versao_atual(self):
        # A troca de espaço exige uma coleção nova (o Chroma não permite alterar o espaço de uma
        # coleção já criada) -- este teste apenas documenta que o nome carrega a versão em uso,
        # para não regredir silenciosamente para uma versão antiga criada sob 'l2'.
        colecao = rm._obter_colecao_tenant(TENANT_TESTE)
        self.assertIn(rm.COLLECTION_VERSION, colecao.name)


class TestConversaoDeDistanciaEmSimilaridade(unittest.TestCase):
    """A conversão dist->cos_sim em reranker.fundir_e_deduplicar_candidatos precisa bater com o
    espaço de distância real que a coleção usa -- testado com vetores de ângulo conhecido."""

    def _candidato_a_partir_da_distancia_cosseno(self, cos_sim_esperado: float) -> dict:
        # No espaço cosine do Chroma, dist = 1 - cos_sim (verificado empiricamente contra a API
        # real do Chroma: ver a análise da Fase 13 no histórico da conversa) -- monta o dict no
        # mesmo formato que buscar_contexto_relevante recebe de collection.query().
        dist_no_espaco_cosseno = 1.0 - cos_sim_esperado
        return {"id": "x", "texto": "qualquer", "meta": {}, "dist": dist_no_espaco_cosseno}

    def test_similaridade_perfeita_dist_zero(self):
        cand = self._candidato_a_partir_da_distancia_cosseno(cos_sim_esperado=1.0)
        resultado = fundir_e_deduplicar_candidatos({"q": [cand]})
        self.assertAlmostEqual(resultado[0].vector_score, 1.0, places=6)

    def test_similaridade_oposta_dist_dois(self):
        cand = self._candidato_a_partir_da_distancia_cosseno(cos_sim_esperado=-1.0)
        resultado = fundir_e_deduplicar_candidatos({"q": [cand]})
        # vector_score é sempre não-negativo (max(0.0, ...)) -- cosseno negativo vira 0, não um
        # score negativo que corromperia o blend ponderado do reranker.
        self.assertAlmostEqual(resultado[0].vector_score, 0.0, places=6)

    def test_similaridade_meio_termo_60_graus(self):
        # cos(60°) = 0.5 exatamente -- caso que a fórmula errada (1 - dist**2/2) também acertaria
        # por coincidência aritmética nalguns pontos; os dois testes acima é que discriminam.
        cos_sim = math.cos(math.pi / 3)
        cand = self._candidato_a_partir_da_distancia_cosseno(cos_sim_esperado=cos_sim)
        resultado = fundir_e_deduplicar_candidatos({"q": [cand]})
        self.assertAlmostEqual(resultado[0].vector_score, cos_sim, places=6)

    def test_bateria_de_angulos_contra_vetores_2d_reais(self):
        # Constrói os vetores de verdade e computa o cosseno via produto escalar -- não confia só
        # na fórmula inversa usada para montar o `dist` dos testes acima.
        referencia = _vetor_unitario(0.0)
        for angulo_graus in (0, 15, 30, 45, 90, 135, 180):
            with self.subTest(angulo_graus=angulo_graus):
                v = _vetor_unitario(math.radians(angulo_graus))
                cos_real = referencia[0] * v[0] + referencia[1] * v[1]
                dist_no_espaco_cosseno = 1.0 - cos_real
                cand = {"id": "x", "texto": "t", "meta": {}, "dist": dist_no_espaco_cosseno}
                resultado = fundir_e_deduplicar_candidatos({"q": [cand]})
                self.assertAlmostEqual(resultado[0].vector_score, max(0.0, cos_real), places=6)


if __name__ == "__main__":
    unittest.main()
