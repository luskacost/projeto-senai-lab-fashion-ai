# -*- coding: utf-8 -*-
"""Sugestões e reportes de erro enviados pelos usuários (Fase 16, Bloco S).

Mesmo padrão de persistência de `conversas_manager.py`: um arquivo JSON por tenant em
`tenant_data/sugestoes/`, protegido por `FileLock` contra escrita concorrente, tenant_id
sanitizado por allowlist (não é UUID, é um slug de configuração -- mesmo padrão de
`conversas_manager._caminho_conversas`/`rag_manager._obter_caminho_chroma`).

Sem e-mail/Slack/integração nenhuma de propósito (decisão do usuário, Fase 16): o destino é um
arquivo revisado manualmente, não uma notificação em tempo real.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

from filelock import FileLock, Timeout

from logger_config import obter_logger

DIRETORIO_SUGESTOES = os.path.join("tenant_data", "sugestoes")
TIMEOUT_LOCK_SEGUNDOS = 5

TIPOS_VALIDOS = ("sugestao", "bug")


def _sanitizar_tenant_id(tenant_id: str) -> str:
    return "".join(c for c in tenant_id if c.isalnum() or c in ("_", "-")).strip() or "default"


def _caminho_sugestoes(tenant_id: str) -> str:
    return os.path.join(DIRETORIO_SUGESTOES, f"{_sanitizar_tenant_id(tenant_id)}.json")


def _caminho_lock_sugestoes(tenant_id: str) -> str:
    return _caminho_sugestoes(tenant_id) + ".lock"


def carregar_sugestoes(tenant_id: str) -> List[Dict[str, Any]]:
    """Lê as sugestões/reportes de um tenant. Lista vazia se o arquivo não existir ou estiver
    corrompido -- nunca quebra o app (mesmo padrão tolerante de `conversas_manager.carregar_conversas`)."""
    caminho_arquivo = _caminho_sugestoes(tenant_id)
    try:
        if os.path.exists(caminho_arquivo):
            with open(caminho_arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return dados
        return []
    except Exception:
        return []


def registrar_sugestao(tenant_id: str, tipo: str, texto: str) -> Dict[str, Any]:
    """Acrescenta uma sugestão/reporte à lista do tenant e persiste. Levanta ValueError se `tipo`
    não for um dos `TIPOS_VALIDOS` ou `texto` vier vazio -- validação na borda, não no meio do
    tolerante `except Exception` de carregar/salvar."""
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"tipo inválido: '{tipo}'. Esperado um de {TIPOS_VALIDOS}.")
    texto_limpo = texto.strip()
    if not texto_limpo:
        raise ValueError("texto não pode ser vazio.")

    registro = {
        "id": str(uuid.uuid4()),
        "tipo": tipo,
        "texto": texto_limpo,
        "criado_em": datetime.now().isoformat(),
    }

    caminho_arquivo = _caminho_sugestoes(tenant_id)
    try:
        os.makedirs(DIRETORIO_SUGESTOES, exist_ok=True)
        with FileLock(_caminho_lock_sugestoes(tenant_id), timeout=TIMEOUT_LOCK_SEGUNDOS):
            sugestoes = carregar_sugestoes(tenant_id)
            sugestoes.append(registro)
            with open(caminho_arquivo, "w", encoding="utf-8") as f:
                json.dump(sugestoes, f, ensure_ascii=False, indent=2)
    except Timeout:
        obter_logger(tenant_id).error(f"Timeout ao adquirir lock de sugestões para tenant={tenant_id} -- registro descartado.")
    except Exception as e:
        obter_logger(tenant_id).error(f"Erro ao salvar sugestão para tenant={tenant_id}: {e}", exc_info=True)

    return registro
