# -*- coding: utf-8 -*-
"""Upload de documento/planilha não bloqueia o event loop (Fase 13, Task 15).

`extrair_documento`/`indexar_documento` (parsing + embeddings) e `carregar_planilha`/
`gerar_resumo_estatistico` são funções síncronas e potencialmente lentas (segundos, num arquivo
grande). Rodá-las direto dentro de um `async def` de rota ocupa a única thread do event loop pela
duração inteira -- toda outra requisição da API, de qualquer tenant (chat incluído), fica parada
até a indexação terminar. `asyncio.to_thread` move o trabalho síncrono para uma thread separada,
liberando o loop para atender outras requisições nesse meio-tempo.

Prova por concorrência real, não por inspeção de código: dispara o upload lento numa thread e uma
rota leve (`GET /documentos`) noutra, e mede se a rota leve termina bem antes do upload synchronous
terminar. Doubles instantâneos no lugar do parsing/embedding de verdade -- este teste é sobre
concorrência do event loop, não sobre extração/indexação em si (já cobertas noutros testes).
"""

import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

TENANT_TESTE = "teste_fase13_upload_concorrente"
ATRASO_SEGUNDOS = 0.5


def _indexar_lento(tenant_id, nome_arquivo, unidades):
    time.sleep(ATRASO_SEGUNDOS)
    return 3


class TestUploadDocumentoNaoBloqueiaEventLoop(unittest.TestCase):

    def test_get_documentos_no_meio_de_um_upload_lento_nao_espera_o_upload(self):
        resultados = {}

        def fazer_upload(client):
            inicio = time.monotonic()
            resposta = client.post(
                "/documentos/upload",
                params={"tenant_id": TENANT_TESTE},
                files={"arquivo": ("manual.txt", b"conteudo qualquer", "text/plain")},
                headers={"X-Admin-Token": "qualquer"},
            )
            resultados["upload"] = (inicio, time.monotonic(), resposta.status_code)

        def fazer_get(client):
            # Garante que o GET começa DEPOIS que o upload já está em voo (dentro do sleep).
            time.sleep(ATRASO_SEGUNDOS / 5)
            inicio = time.monotonic()
            resposta = client.get("/documentos", params={"tenant_id": TENANT_TESTE})
            resultados["get"] = (inicio, time.monotonic(), resposta.status_code)

        with patch("api.main.verificar_token_admin", return_value=None), \
             patch("api.main.extrair_documento", return_value=[{"texto": "x"}]), \
             patch("api.main.indexar_documento", side_effect=_indexar_lento), \
             patch("api.main.listar_documentos_indexados", return_value=[]):
            with TestClient(app) as client:
                t_upload = threading.Thread(target=fazer_upload, args=(client,))
                t_get = threading.Thread(target=fazer_get, args=(client,))
                t_upload.start()
                t_get.start()
                t_upload.join(timeout=5)
                t_get.join(timeout=5)

        self.assertEqual(resultados["upload"][2], 200)
        self.assertEqual(resultados["get"][2], 200)

        duracao_get = resultados["get"][1] - resultados["get"][0]
        # Sem asyncio.to_thread, o GET só rodaria depois que o upload liberasse o event loop --
        # ou seja, duracao_get >= ATRASO_SEGUNDOS (menos o pequeno atraso inicial). Com a correção,
        # o GET termina quase instantaneamente mesmo com o upload ainda dormindo.
        self.assertLess(
            duracao_get, ATRASO_SEGUNDOS * 0.6,
            f"GET /documentos levou {duracao_get:.3f}s -- parece ter esperado o upload lento "
            "(event loop bloqueado pela indexação síncrona).",
        )


if __name__ == "__main__":
    unittest.main()
