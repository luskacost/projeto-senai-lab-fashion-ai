# -*- coding: utf-8 -*-
"""Testes dos mecanismos de classificação de metadado, injeção de texto e alinhamento de
variante -- agora configuráveis por tenant, com default vazio (Fase 13, Task 3).

## O que este arquivo prova

Antes desta task, `rag_manager._inferir_metadados_trecho` e o bloco de metadata_score do
`reranker.HeuristicReranker` tinham vocabulário têxtil hardcoded (seção/produto/modelo/variante
de UM documento específico -- Millie Denim/M518 -- que não está mais na base de produção) e uma
regra de disambiguação de "gola" idiossincrática o bastante para não valer a pena generalizar
(removida, não substituída). Isso foi extraído para `RAG_CONFIG`, com dois testes centrais:

1. **Default vazio não classifica nem ajusta nada** -- prova que a extração não deixou um
   comportamento invisível ligado por engano.
2. **Configurado, o mecanismo genérico reproduz o mesmo tipo de resultado** que o código
   hardcoded produzia -- prova que a generalização não perdeu a capacidade, só a tornou opt-in.
"""

import unittest

import rag_manager as rm
from rag_config import RAG_CONFIG
from reranker import CandidateChunk, _score_alinhamento_de_variante
from query_engine import normalizar_texto


class TestClassificacaoDeMetadadoDefaultVazio(unittest.TestCase):

    def setUp(self):
        self._original = RAG_CONFIG.get("metadata_keyword_rules")
        RAG_CONFIG["metadata_keyword_rules"] = {}

    def tearDown(self):
        RAG_CONFIG["metadata_keyword_rules"] = self._original

    def test_texto_repleto_de_vocabulario_textil_nao_classifica_nada_sem_config(self):
        texto = (
            "FICHA TÉCNICA: Camisa Feminina Jeans, Tecido Millie Denim Maskskin, "
            "Composição 100% Liocel, Variante M518."
        )
        meta = rm._inferir_metadados_trecho(texto)
        self.assertEqual(meta, {})


class TestClassificacaoDeMetadadoConfigurada(unittest.TestCase):

    def setUp(self):
        self._original = RAG_CONFIG.get("metadata_keyword_rules")
        RAG_CONFIG["metadata_keyword_rules"] = {
            "produto": {"Camisa": ["CAMISA"], "Calça": ["CALÇA"]},
            "variante": {"Jeans": ["JEANS"], "Social": ["SOCIAL"]},
        }

    def tearDown(self):
        RAG_CONFIG["metadata_keyword_rules"] = self._original

    def test_classifica_conforme_as_regras_configuradas(self):
        meta = rm._inferir_metadados_trecho("Uma Camisa Jeans azul.")
        self.assertEqual(meta["produto"], "Camisa")
        self.assertEqual(meta["variante"], "Jeans")

    def test_campo_sem_termo_correspondente_fica_ausente(self):
        meta = rm._inferir_metadados_trecho("Uma Calça qualquer, sem menção de variante.")
        self.assertEqual(meta["produto"], "Calça")
        self.assertNotIn("variante", meta)

    def test_primeiro_rotulo_que_bate_na_ordem_declarada_vence(self):
        # "Social" está declarado depois de "Jeans" -- um texto com as duas palavras fica com
        # "Jeans" (ordem de inserção do dict, documentado como contrato do mecanismo).
        meta = rm._inferir_metadados_trecho("Camisa Jeans Social combinada.")
        self.assertEqual(meta["variante"], "Jeans")


class TestInjecaoDeTextoDefaultVazia(unittest.TestCase):

    def setUp(self):
        self._original = RAG_CONFIG.get("chunk_text_injection_rules")
        RAG_CONFIG["chunk_text_injection_rules"] = []

    def tearDown(self):
        RAG_CONFIG["chunk_text_injection_rules"] = self._original

    def test_sem_regras_o_texto_do_chunk_nao_muda(self):
        texto = "Tecido especial sem menção explícita à variante."
        resultado = rm._aplicar_injecoes_de_texto(texto, {"variante": "Jeans"})
        self.assertEqual(resultado, texto)


class TestInjecaoDeTextoConfigurada(unittest.TestCase):

    def setUp(self):
        self._original = RAG_CONFIG.get("chunk_text_injection_rules")
        RAG_CONFIG["chunk_text_injection_rules"] = [{
            "quando_metadado": {"campo": "variante", "rotulo": "Jeans"},
            "texto_injetado": "PRODUTO: Camisa Jeans",
            "somente_se_ausente_termos": ["jeans"],
        }]

    def tearDown(self):
        RAG_CONFIG["chunk_text_injection_rules"] = self._original

    def test_injeta_quando_metadado_bate_e_termo_esta_ausente(self):
        texto = "Tecido Millie Denim Maskskin, lavagem clara."
        resultado = rm._aplicar_injecoes_de_texto(texto, {"variante": "Jeans"})
        self.assertTrue(resultado.startswith("PRODUTO: Camisa Jeans"))
        self.assertIn(texto, resultado)

    def test_nao_injeta_se_o_termo_ja_estiver_presente(self):
        texto = "Camisa jeans com lavagem clara."
        resultado = rm._aplicar_injecoes_de_texto(texto, {"variante": "Jeans"})
        self.assertEqual(resultado, texto)

    def test_nao_injeta_se_o_metadado_nao_bater(self):
        texto = "Tecido qualquer."
        resultado = rm._aplicar_injecoes_de_texto(texto, {"variante": "Social"})
        self.assertEqual(resultado, texto)


def _candidato(texto: str, metadata: dict) -> CandidateChunk:
    return CandidateChunk(chunk_id="x", texto=texto, metadata=metadata)


class TestAlinhamentoDeVarianteDefaultVazio(unittest.TestCase):

    def test_sem_regras_configuradas_nunca_ajusta_o_score(self):
        cand = _candidato("Camisa jeans azul", {"variante": "Jeans"})
        ajuste = _score_alinhamento_de_variante(
            normalizar_texto("quero uma camisa jeans"), normalizar_texto(cand.texto),
            cand.metadata, regras=[],
        )
        self.assertEqual(ajuste, 0.0)


class TestAlinhamentoDeVarianteConfigurado(unittest.TestCase):

    REGRAS = [{
        "campo_metadado": "variante",
        "grupos": {"jeans": ["jeans", "millie"], "m518": ["m518"]},
        "bonus": 0.25,
        "penalidade": 0.40,
    }]

    def _ajuste(self, query: str, texto_chunk: str, metadata: dict) -> float:
        return _score_alinhamento_de_variante(
            normalizar_texto(query), normalizar_texto(texto_chunk), metadata, self.REGRAS,
        )

    def test_bonus_quando_query_e_chunk_pedem_o_mesmo_grupo(self):
        ajuste = self._ajuste("qual o tecido da camisa jeans", "Tecido Millie Denim", {"variante": "Jeans"})
        self.assertAlmostEqual(ajuste, 0.25)

    def test_penalidade_quando_chunk_e_de_outro_grupo_do_mesmo_eixo(self):
        ajuste = self._ajuste("qual o tecido da camisa jeans", "Tecido M518 tradicional", {"variante": "M518"})
        self.assertAlmostEqual(ajuste, -0.40)

    def test_sem_ajuste_quando_a_query_nao_menciona_nenhum_grupo_do_eixo(self):
        ajuste = self._ajuste("qual o preço da camisa", "Tecido M518 tradicional", {"variante": "M518"})
        self.assertEqual(ajuste, 0.0)

    def test_comparacao_explicita_bonifica_sem_penalizar(self):
        # "diferença entre jeans e m518" menciona os dois grupos -- qualquer um dos dois lados
        # ganha bônus, nenhum leva penalidade (a pergunta já reconhece a existência de ambos).
        ajuste_jeans = self._ajuste("diferença entre jeans e m518", "Tecido Millie Denim", {"variante": "Jeans"})
        ajuste_m518 = self._ajuste("diferença entre jeans e m518", "Tecido M518", {"variante": "M518"})
        self.assertAlmostEqual(ajuste_jeans, 0.25)
        self.assertAlmostEqual(ajuste_m518, 0.25)

    def test_chunk_que_nao_bate_com_nenhum_grupo_fica_neutro(self):
        ajuste = self._ajuste("qual o tecido da camisa jeans", "Etiqueta de composição do fio", {})
        self.assertEqual(ajuste, 0.0)


if __name__ == "__main__":
    unittest.main()
