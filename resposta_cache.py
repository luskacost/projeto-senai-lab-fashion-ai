# -*- coding: utf-8 -*-
"""Módulo de gerenciamento de cache de respostas para Perguntas Rápidas do Senai LabFashion IA."""

import os
import json
import hashlib
from datetime import datetime, timedelta
from logger_config import obter_logger


def gerar_chave_cache(tenant_id: str, modo: str, pergunta: str) -> str:
    """Gera uma chave determinística e normalizada via MD5 para identificar uma pergunta no cache."""
    normalizado = f"{tenant_id}|{modo}|{pergunta.strip().lower()}"
    return hashlib.md5(normalizado.encode("utf-8")).hexdigest()


def obter_resposta_cacheada(tenant_id: str, modo: str, pergunta: str, validade_horas: int) -> str | None:
    """Lê o arquivo de cache do tenant e retorna a resposta se o timestamp salvo estiver dentro do prazo de validade.

    Em caso de erro, expiração ou arquivo inexistente, retorna None.
    """
    if validade_horas <= 0:
        return None

    caminho_arquivo = os.path.join("tenant_data", f"{tenant_id}_cache.json")
    if not os.path.exists(caminho_arquivo):
        return None

    try:
        with open(caminho_arquivo, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return None

        chave = gerar_chave_cache(tenant_id, modo, pergunta)
        entrada = data.get(chave)

        if not entrada or not isinstance(entrada, dict):
            return None

        salvo_em_str = entrada.get("salvo_em")
        if not salvo_em_str:
            return None

        salvo_em = datetime.fromisoformat(salvo_em_str)
        agora = datetime.now()

        # Verifica se está dentro do prazo de validade
        if agora >= salvo_em and (agora - salvo_em) <= timedelta(hours=validade_horas):
            logger = obter_logger(tenant_id)
            logger.info(f"Resposta servida via cache para o modo '{modo}' (salvo em: {salvo_em_str})")
            return entrada.get("resposta")

        return None
    except Exception as e:
        logger = obter_logger(tenant_id)
        logger.error(f"Erro ao ler/parsear arquivo de cache de respostas: {e}", exc_info=True)
        return None


def salvar_resposta_cache(tenant_id: str, modo: str, pergunta: str, resposta: str):
    """Salva ou atualiza a entrada no arquivo JSON do tenant, fazendo merge com o conteúdo existente."""
    try:
        os.makedirs("tenant_data", exist_ok=True)
        caminho_arquivo = os.path.join("tenant_data", f"{tenant_id}_cache.json")

        data = {}
        if os.path.exists(caminho_arquivo):
            try:
                with open(caminho_arquivo, "r", encoding="utf-8") as f:
                    conteudo = json.load(f)
                    if isinstance(conteudo, dict):
                        data = conteudo
            except Exception:
                data = {}

        chave = gerar_chave_cache(tenant_id, modo, pergunta)
        data[chave] = {
            "pergunta": pergunta,
            "resposta": resposta,
            "salvo_em": datetime.now().isoformat()
        }

        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger = obter_logger(tenant_id)
        logger.info(f"Nova resposta armazenada no cache para o modo '{modo}'")
    except Exception as e:
        logger = obter_logger(tenant_id)
        logger.error(f"Erro ao salvar resposta no arquivo de cache: {e}", exc_info=True)

