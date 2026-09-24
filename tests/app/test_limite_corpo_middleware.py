# -*- coding: utf-8 -*-
"""Middleware de limite de tamanho do corpo da requisição (Fase 15, V7).

Antes: `/documentos/upload` e `/planilha/upload` só checavam `len(conteudo) > LIMITE_UPLOAD_BYTES`
depois de `await arquivo.read()` -- mas o parser multipart do Starlette já grava o arquivo inteiro
num `SpooledTemporaryFile` sem limite próprio, ANTES da rota rodar. Testado aqui no nível ASGI puro
(sem TestClient/app real) porque simular um upload de dezenas de MB só para provar o limite seria
lento e não isolaria a peça que importa: o middleware precisa abortar a leitura do corpo assim que
o total acumulado ultrapassa o limite, não depois.
"""

import unittest

from limite_corpo_middleware import LimiteTamanhoDoCorpoMiddleware


def _scope_http() -> dict:
    return {"type": "http", "method": "POST", "path": "/documentos/upload"}


class TestLimiteTamanhoDoCorpoMiddleware(unittest.IsolatedAsyncioTestCase):

    async def test_corpo_dentro_do_limite_passa_intacto(self):
        mensagens_recebidas_pelo_app = []

        async def app_downstream(scope, receive, send):
            while True:
                msg = await receive()
                mensagens_recebidas_pelo_app.append(msg)
                if not msg.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = LimiteTamanhoDoCorpoMiddleware(app_downstream, limite_bytes=1000)

        partes = [b"a" * 400, b"b" * 400]

        async def receive():
            if partes:
                pedaco = partes.pop(0)
                return {"type": "http.request", "body": pedaco, "more_body": bool(partes)}
            return {"type": "http.request", "body": b"", "more_body": False}

        respostas = []

        async def send(msg):
            respostas.append(msg)

        await middleware(_scope_http(), receive, send)

        self.assertEqual(len(mensagens_recebidas_pelo_app), 2)
        self.assertEqual(respostas[0]["status"], 200)

    async def test_corpo_acima_do_limite_e_abortado_com_413_antes_do_app_terminar_de_ler(self):
        pedacos_recebidos_pelo_app = []

        async def app_downstream(scope, receive, send):
            # Simula o parser multipart do Starlette: fica lendo até `more_body` virar False.
            # Se o middleware não abortar antes, este loop nunca sai (ou processa dados demais).
            while True:
                msg = await receive()
                pedacos_recebidos_pelo_app.append(msg["body"])
                if not msg.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"nunca deveria chegar aqui"})

        middleware = LimiteTamanhoDoCorpoMiddleware(app_downstream, limite_bytes=1000)

        # 3 blocos de 500 bytes = 1500 no total -- estoura o limite de 1000 no segundo bloco.
        partes = [b"a" * 500, b"b" * 500, b"c" * 500]

        async def receive():
            if partes:
                pedaco = partes.pop(0)
                return {"type": "http.request", "body": pedaco, "more_body": bool(partes)}
            return {"type": "http.request", "body": b"", "more_body": False}

        respostas = []

        async def send(msg):
            respostas.append(msg)

        await middleware(_scope_http(), receive, send)

        # O app nunca viu o terceiro bloco -- a exceção interrompeu a leitura no meio.
        self.assertEqual(len(pedacos_recebidos_pelo_app), 2)

        inicio = next(r for r in respostas if r["type"] == "http.response.start")
        self.assertEqual(inicio["status"], 413)

    async def test_requisicao_nao_http_passa_direto_sem_contagem(self):
        chamado = {"valor": False}

        async def app_downstream(scope, receive, send):
            chamado["valor"] = True

        middleware = LimiteTamanhoDoCorpoMiddleware(app_downstream, limite_bytes=10)

        async def receive():
            return {"type": "websocket.connect"}

        async def send(msg):
            pass

        await middleware({"type": "websocket"}, receive, send)
        self.assertTrue(chamado["valor"])


if __name__ == "__main__":
    unittest.main()
