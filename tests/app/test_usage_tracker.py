# -*- coding: utf-8 -*-
"""Testes de usage_tracker.py -- sem arquivo dedicado até a Fase 10, Task 8, quando o módulo
passou a sustentar um segundo limite diário (buscas_web) além de mensagens/imagens, tornando
importante confirmar que o "tipo" é de fato genérico (qualquer chave nova funciona sem precisar
alterar usage_tracker.py) e não só um acaso de implementação.

Usa um tenant_id fictício e próprio (não compartilhado com nenhum outro teste/uso real) para não
colidir com tenant_data/senai_labfashion_usage.json; remove o arquivo de uso e o lock no
tearDown para não deixar debris em tenant_data/.
"""

import json
import os
import unittest
from unittest.mock import patch

from filelock import Timeout

import usage_tracker
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


class TestFailClosedEmErroDeLeitura(unittest.TestCase):
    """Fase 14, Bloco S, Task 3: um arquivo de uso corrompido não pode virar licença ilimitada.

    `verificar_limite` (usado para DECIDIR se libera) precisa negar quando não consegue ler o
    contador de verdade; `carregar_uso_do_dia` (usado só para EXIBIR uso) continua tolerante,
    devolvendo zero -- comportamento antigo, preservado de propósito para não quebrar uma tela
    que só quer mostrar "uso de hoje" sem travar a aplicação por um arquivo ruim.
    """

    def setUp(self):
        os.makedirs("tenant_data", exist_ok=True)

    def tearDown(self):
        for caminho in (_caminho_uso(), _caminho_lock()):
            if os.path.exists(caminho):
                os.remove(caminho)

    def _corromper_arquivo_de_uso(self):
        with open(_caminho_uso(), "w", encoding="utf-8") as f:
            f.write("{ isto nao e json valido")

    def test_verificar_limite_nega_com_arquivo_corrompido(self):
        self._corromper_arquivo_de_uso()
        self.assertFalse(verificar_limite(TENANT_TESTE, "mensagens", limite=200))

    def test_verificar_limite_nega_quando_conteudo_nao_e_objeto(self):
        with open(_caminho_uso(), "w", encoding="utf-8") as f:
            f.write("[1, 2, 3]")
        self.assertFalse(verificar_limite(TENANT_TESTE, "mensagens", limite=200))

    def test_carregar_uso_do_dia_continua_tolerante_com_arquivo_corrompido(self):
        # Contraste deliberado com o teste acima: a versão de EXIBIÇÃO não nega, só zera.
        self._corromper_arquivo_de_uso()
        uso = carregar_uso_do_dia(TENANT_TESTE)
        self.assertEqual(uso.get("mensagens"), 0)

    def test_arquivo_inexistente_nao_e_tratado_como_erro(self):
        # Não pode confundir "nunca usou hoje" (normal) com "não consigo ler" (falha) -- sem
        # arquivo nenhum, verificar_limite libera normalmente.
        self.assertTrue(verificar_limite(TENANT_TESTE, "mensagens", limite=200))

    def test_dia_anterior_nao_e_tratado_como_erro(self):
        with open(_caminho_uso(), "w", encoding="utf-8") as f:
            json.dump({"data": "2000-01-01", "mensagens": 199}, f)
        # Data antiga é reset normal (virou o dia), não falha -- 0 de uso hoje, dentro do limite.
        self.assertTrue(verificar_limite(TENANT_TESTE, "mensagens", limite=200))


class TestRetentativaDeIncremento(unittest.TestCase):
    """Fase 14, Bloco S, Task 3: contenção momentânea no lock não pode descartar o incremento na
    primeira tentativa -- só depois de esgotar as retentativas."""

    def tearDown(self):
        for caminho in (_caminho_uso(), _caminho_lock()):
            if os.path.exists(caminho):
                os.remove(caminho)

    def _fake_filelock(self, timeouts_antes_de_funcionar):
        """Substitui usage_tracker.FileLock por um dublê que levanta Timeout nas N primeiras
        tentativas e só então se comporta como o FileLock de verdade."""
        chamadas = {"n": 0}
        FileLockReal = usage_tracker.FileLock

        class FileLockComFalhaInicial:
            def __init__(self, *args, **kwargs):
                self._real = FileLockReal(*args, **kwargs)

            def __enter__(self):
                chamadas["n"] += 1
                if chamadas["n"] <= timeouts_antes_de_funcionar:
                    raise Timeout("lock de teste")
                return self._real.__enter__()

            def __exit__(self, *exc):
                return self._real.__exit__(*exc)

        return FileLockComFalhaInicial, chamadas

    def test_recupera_apos_timeout_transitorio(self):
        fake, chamadas = self._fake_filelock(timeouts_antes_de_funcionar=1)
        with patch.object(usage_tracker, "FileLock", fake):
            incrementar_uso(TENANT_TESTE, "mensagens")
        self.assertEqual(chamadas["n"], 2)  # 1 timeout + 1 sucesso
        self.assertEqual(carregar_uso_do_dia(TENANT_TESTE).get("mensagens"), 1)

    def test_desiste_apos_esgotar_tentativas_sem_lancar_excecao(self):
        fake, chamadas = self._fake_filelock(timeouts_antes_de_funcionar=99)
        with patch.object(usage_tracker, "FileLock", fake):
            incrementar_uso(TENANT_TESTE, "mensagens")  # não deve levantar
        self.assertEqual(chamadas["n"], usage_tracker.MAX_TENTATIVAS_INCREMENTO)
        # Nenhum arquivo válido foi escrito -- o incremento foi mesmo descartado, como o log diz.
        self.assertEqual(carregar_uso_do_dia(TENANT_TESTE).get("mensagens"), 0)


if __name__ == "__main__":
    unittest.main()
