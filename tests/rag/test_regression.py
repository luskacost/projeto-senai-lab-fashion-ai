# -*- coding: utf-8 -*-
"""Runner de Testes de Regressão e Benchmark Automatizado do RAG.

Carrega `test_cases.json`, executa o pipeline em ambiente controlado,
classifica eventuais falhas (RETRIEVAL, RERANKING, GENERATION, HALLUCINATION)
e produz o relatório estruturado de validação.
"""

import json
import os
import shutil
import sys
import unittest

from rag_manager import (
    indexar_documento,
    buscar_contexto_relevante,
    formatar_bloco_debug_rag,
    obter_ultimo_rag_debug
)

DOC_CONCEITUAL_PAG_1 = """PROCESSAMENTO DE LINGUAGEM NATURAL E DESAMBIGUAÇÃO:
O contexto é fundamental para interpretar palavras polissêmicas ou ambíguas como 'banco', que pode significar tanto uma instituição financeira quanto um assento físico.
Sistemas de Inteligência Artificial utilizam a análise do contexto textual ao redor das palavras para realizar a correta desambiguação semântica, reduzindo ambiguidades e determinando o significado preciso na frase."""

DOC_CONCEITUAL_PAG_2 = """VALIDAÇÃO CRUZADA E MACHINE LEARNING:
O método K-Fold Cross-Validation divide o conjunto de dados em K partições iterativas para treinar e validar o modelo.
Essa técnica é essencial para proteger contra overfitting (sobreajuste), pois testa o modelo em folds não vistos;
mitiga riscos de data leakage (vazamento de dados) ao isolar transformações dentro de cada fold;
e auxilia na identificação de concept drift (deriva de conceito) ao avaliar a estabilidade do modelo através das partições."""

DOC_CONCEITUAL_PAG_3 = """COMPARAÇÃO ENTRE ARQUITETURAS DE LINGUAGEM:
Large Language Models (LLMs) operam com dezenas a centenas de bilhões de parâmetros, demandando hardware corporativo com clusters de GPUs e infraestrutura em nuvem, sendo indicados para raciocínio generalista complexo.
Por outro lado, Small Language Models (SLMs) possuem faixa de 1 a 7 bilhões de parâmetros, possibilitam execução local em edge devices e hardware modesto, com baixíssimo consumo de memória e foco em tarefas especializadas."""

DOC_CONCEITUAL_PAG_4 = """FICHA TÉCNICA TÊXTIL E ESPECIFICAÇÕES DE MATERIAIS:
Modelo Base Tradicional: Tecido M518, gramatura 128 g/m², largura 145 cm, composição 100% Algodão.
Variante Camisa Jeans: Tecido Millie Denim Maskskin, gramatura 4,5 oz, largura 172 cm, composição 100% Liocel, lavagem clara."""


def executar_benchmark_completo():
    """Executa a suite completa de casos de teste e imprime o relatório estruturado."""
    tenant_id = "test_regression_suite"
    caminho_chroma = os.path.join("tenant_data", "chroma", tenant_id)
    if os.path.exists(caminho_chroma):
        shutil.rmtree(caminho_chroma, ignore_errors=True)

    # Indexa base de dados com cenários conceituais, comparativos, multi-conceito e numéricos
    paginas = [
        {"pagina": 1, "texto": DOC_CONCEITUAL_PAG_1},
        {"pagina": 2, "texto": DOC_CONCEITUAL_PAG_2},
        {"pagina": 3, "texto": DOC_CONCEITUAL_PAG_3},
        {"pagina": 4, "texto": DOC_CONCEITUAL_PAG_4}
    ]
    indexar_documento(tenant_id, "documento_benchmark.pdf", paginas)

    # Carrega casos de teste
    cases_path = os.path.join(os.path.dirname(__file__), "test_cases.json")
    with open(cases_path, "r", encoding="utf-8") as f:
        casos = json.load(f)

    print("\n" + "=" * 60)
    print("RELATÓRIO DE AVALIAÇÃO AUTOMATIZADA DO PIPELINE RAG")
    print("=" * 60)

    total_pass = 0
    total_fail = 0

    for c in casos:
        q_id = c["id"]
        pergunta = c["question"]
        categoria = c["category"]
        expected_terms = c.get("expected_terms", [])
        expected_pages = c.get("expected_pages", [])
        should_answer = c.get("should_answer", True)

        resultados = buscar_contexto_relevante(tenant_id, pergunta, top_k=5)
        textos_recuperados = [r["texto"] for r in resultados]
        texto_total_recuperado = " ".join(textos_recuperados).lower()
        paginas_recuperadas = [r["pagina"] for r in resultados]

        status = "PASS"
        failure_type = "NONE"

        if should_answer:
            # Verifica se recuperou algum chunk
            if not resultados:
                status = "FAIL"
                failure_type = "RETRIEVAL FAILURE (Nenhum chunk recuperado)"
            else:
                # Verifica cobertura dos termos esperados
                termos_ausentes = [t for t in expected_terms if t.lower() not in texto_total_recuperado]
                if len(termos_ausentes) > len(expected_terms) * 0.4:
                    status = "FAIL"
                    failure_type = f"RETRIEVAL FAILURE (Termos ausentes: {termos_ausentes})"
                elif expected_pages and not any(p in paginas_recuperadas for p in expected_pages):
                    status = "FAIL"
                    failure_type = "RERANKING FAILURE (Página correta não selecionada no top)"
        else:
            # Teste de não-alucinação / pergunta sem resposta
            # O sistema deve retornar lista vazia ou chunks sem correlação espúria
            if any(termo in texto_total_recuperado for termo in ["preço", "fornecedor", "r$"]):
                status = "FAIL"
                failure_type = "HALLUCINATION / CORRELAÇÃO ESPÚRIA"

        if status == "PASS":
            total_pass += 1
        else:
            total_fail += 1

        print(f"\nQUESTION: {pergunta}")
        print(f"CATEGORY: {categoria.upper()}")
        print(f"EXPECTED TERMS: {expected_terms if expected_terms else 'Nenhum (Sem evidência)'}")
        print(f"RETRIEVED PAGES: {paginas_recuperadas}")
        print(f"EXPECTED EVIDENCE RETRIEVED: {'YES' if status == 'PASS' else 'NO'}")
        print(f"STATUS: {status}")
        if failure_type != "NONE":
            print(f"FAILURE TYPE: {failure_type}")
        print("-" * 50)

    print("\n" + "=" * 60)
    print(f"RESUMO: {total_pass} PASS | {total_fail} FAIL (Total: {len(casos)} testes)")
    print("=" * 60 + "\n")

    # Limpeza
    if os.path.exists(caminho_chroma):
        shutil.rmtree(caminho_chroma, ignore_errors=True)

    return total_fail == 0


class TestRegressionSuite(unittest.TestCase):
    def test_run_all_cases(self):
        sucesso = executar_benchmark_completo()
        self.assertTrue(sucesso, "Alguns casos de teste falharam no benchmark RAG.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
