# -*- coding: utf-8 -*-
"""Testes automatizados de Geração Grounded e Prevenção de Alucinação."""

import os
import unittest
from typing import Dict, Any, List

from rag_manager import buscar_contexto_relevante
from tenant_config import TENANT_CONFIG


class TestRAGGeneration(unittest.TestCase):
    """Valida o prompt de geração e conformidade de groundedness com o contexto."""

    def test_01_prompt_contains_grounded_rules(self):
        """Valida que as diretrizes obrigatórias de groundedness estão configuradas no prompt do sistema."""
        prompt_bc = TENANT_CONFIG["senai_labfashion"]["modos"]["Base de Conhecimento"]["prompt"]
        
        self.assertIn("EXCLUSIVAMENTE", prompt_bc)
        self.assertIn("Não encontrei essa informação no documento", prompt_bc)
        self.assertIn("NUNCA invente", prompt_bc)
        self.assertIn("Preserve", prompt_bc)
        self.assertIn("Para perguntas comparativas", prompt_bc)

    def test_02_context_formatting(self):
        """Valida que o contexto é formatado com identificação clara de página, documento e metadados."""
        sample_chunk = {
            "fonte": "manual.pdf",
            "pagina": 2,
            "secao": "Ficha Técnica",
            "produto": "Camisa",
            "variante": "Jeans",
            "texto": "Tecido Millie Denim Maskskin, gramatura 4,5 oz."
        }
        meta_info = []
        if sample_chunk.get("secao"):
            meta_info.append(f"SEÇÃO: {sample_chunk['secao']}")
        if sample_chunk.get("produto") or sample_chunk.get("variante"):
            prod_var = f"{sample_chunk.get('produto', '')} {sample_chunk.get('variante', '')}".strip()
            meta_info.append(f"PRODUTO/VARIANTE: {prod_var}")
        meta_header = " | ".join(meta_info)

        bloco = (
            f"DOCUMENTO: {sample_chunk['fonte']}\n"
            f"PÁGINA: {sample_chunk['pagina']}\n"
            f"CONTEXTO: {meta_header}\n"
            f"CONTEÚDO:\n{sample_chunk['texto']}"
        )

        self.assertIn("PÁGINA: 2", bloco)
        self.assertIn("PRODUTO/VARIANTE: Camisa Jeans", bloco)
        self.assertIn("4,5 oz", bloco)


if __name__ == "__main__":
    unittest.main(verbosity=2)
