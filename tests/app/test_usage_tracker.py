# -*- coding: utf-8 -*-
"""Testes de usage_tracker.py -- sem arquivo dedicado até a Fase 10, Task 8, quando o módulo
passou a sustentar um segundo limite diário (buscas_web) além de mensagens/imagens, tornando
importante confirmar que o "tipo" é de fato genérico (qualquer chave nova funciona sem precisar
alterar usage_tracker.py) e não só um acaso de implementação.

Usa um tenant_id fictício e próprio (não compartilhado com nenhum outro teste/uso real) para não
colidir com tenant_data/senai_labfashion_usage.json; remove o arquivo de uso e o lock no
tearDown para não deixar debris em tenant_data/.
"""

import os
import unittest

from usage_tracker import incrementar_uso, verificar_limite, carregar_uso_do_dia

TENANT_TESTE = "teste_task8_usage_tracker"


def _caminho_uso() -> str:
    return os.path.join("tenant_data", f"{TENANT_TESTE}_usage.json")


def _caminho_lock() -> str:
    return os.path.join("tenant_data", f"{TENANT_TESTE}_usage.json.lock")


class TestTipoGenerico(unittest.TestCase):
    """usage_tracker não tem uma lista fixa de "tipos" válidos -- mensagens/imagens são só os
    únicos usados até a Task 8; buscas_web precisa funcionar sem nenhuma mudança no módulo."""

    def tearDown(self):
        for caminho in (_caminho_uso(), _caminho_lock()):
            if os.path.exists(caminho):
                os.remove(caminho)

    def test_incrementar_tipo_novo_comeca_do_zero(self):
        incrementar_uso(TENANT_TESTE, "buscas_web")
        uso = carregar_uso_do_dia(TENANT_TESTE)
        self.assertEqual(uso.get("buscas_web"), 1)

    def test_incrementar_tipo_novo_acumula(self):
        incrementar_uso(TENANT_TESTE, "buscas_web")
        incrementar_uso(TENANT_TESTE, "buscas_web")
        incrementar_uso(TENANT_TESTE, "buscas_web")
        uso = carregar_uso_do_dia(TENANT_TESTE)
        self.assertEqual(uso.get("buscas_web"), 3)

    def test_tipo_novo_nao_afeta_mensagens_e_imagens(self):
        incrementar_uso(TENANT_TESTE, "mensagens")
        incrementar_uso(TENANT_TESTE, "buscas_web")
        uso = carregar_uso_do_dia(TENANT_TESTE)
        self.assertEqual(uso.get("mensagens"), 1)
        self.assertEqual(uso.get("imagens"), 0)
        self.assertEqual(uso.get("buscas_web"), 1)

    def test_verificar_limite_tipo_ausente_no_arquivo_e_permitido(self):
        # Nenhuma chamada de incrementar_uso ainda ocorreu para este tenant nesta execução --
        # carregar_uso_do_dia nem tem a chave "buscas_web" no dict padrão.
        self.assertTrue(verificar_limite(TENANT_TESTE, "buscas_web", limite=50))

    def test_verificar_limite_bloqueia_quando_atingido(self):
        for _ in range(3):
            incrementar_uso(TENANT_TESTE, "buscas_web")
        self.assertFalse(verificar_limite(TENANT_TESTE, "buscas_web", limite=3))
        self.assertTrue(verificar_limite(TENANT_TESTE, "buscas_web", limite=4))


if __name__ == "__main__":
    unittest.main()
