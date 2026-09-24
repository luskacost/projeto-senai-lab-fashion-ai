# -*- coding: utf-8 -*-
"""Middleware ASGI que limita o tamanho do corpo de qualquer requisição (Fase 15, V7).

Por que não basta checar `len(await arquivo.read())` dentro da rota (o que o código fazia até
aqui): o parser multipart do Starlette (`starlette.formparsers.MultiPartParser`) grava cada parte
de arquivo incrementalmente num `SpooledTemporaryFile` **sem limite próprio de tamanho** -- só
limita partes que não são arquivo (campos de texto comuns, via `max_part_size`, hoje 1MB). Isso
acontece durante a resolução da dependência `UploadFile` do FastAPI, **antes** do corpo da rota
rodar. Ou seja: um upload de qualquer tamanho já foi recebido e gravado (em memória e depois em
disco) no momento em que `await arquivo.read()` é chamado -- checar o tamanho ali só evita o
processamento (parsing/indexação) do arquivo grande, não o consumo de memória/disco de recebê-lo.

A única forma de limitar de verdade é interceptar os bytes crus da conexão, antes que o parser de
formulário (ou qualquer outro código) os consuma. Um middleware ASGI puro (não
`BaseHTTPMiddleware`, que também bufferiza o corpo inteiro antes de repassar) envolve o callable
`receive` e aborta assim que o total acumulado ultrapassa o limite -- a exceção interrompe a
leitura do corpo no meio, então o parser nunca recebe os bytes restantes.
"""

import json
from typing import Any, Awaitable, Callable, Dict

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]


class _CorpoExcedeuLimite(Exception):
    pass


class LimiteTamanhoDoCorpoMiddleware:
    """Aborta com 413 qualquer requisição HTTP cujo corpo ultrapasse `limite_bytes`, contando os
    bytes conforme chegam -- não depois de já terem sido recebidos por inteiro."""

    def __init__(self, app: Callable, limite_bytes: int) -> None:
        self.app = app
        self.limite_bytes = limite_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        total = 0
        limite = self.limite_bytes

        async def receive_com_limite() -> Dict[str, Any]:
            nonlocal total
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                total += len(mensagem.get("body", b""))
                if total > limite:
                    raise _CorpoExcedeuLimite()
            return mensagem

        try:
            await self.app(scope, receive_com_limite, send)
        except _CorpoExcedeuLimite:
            corpo = json.dumps(
                {"detail": f"Corpo da requisição excede o limite de {limite // (1024 * 1024)}MB."}
            ).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": corpo})
