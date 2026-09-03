# -*- coding: utf-8 -*-
"""Módulo de controle e rastreamento de limite de uso por tenant."""

import os
import json
from datetime import datetime
from logger_config import obter_logger

def carregar_uso_do_dia(tenant_id: str) -> dict:
    """Lê o arquivo tenant_data/{tenant_id}_usage.json.
    
    Se o arquivo não existir, for inválido ou tiver data diferente de hoje (YYYY-MM-DD),
    retorna um dicionário zerado no formato:
    {"data": "AAAA-MM-DD", "mensagens": 0, "imagens": 0}
    sem modificar o disco.
    """
    hoje = datetime.now().strftime('%Y-%m-%d')
    dict_padrao = {"data": hoje, "mensagens": 0, "imagens": 0}

    try:
        caminho_arquivo = os.path.join("tenant_data", f"{tenant_id}_usage.json")
        if not os.path.exists(caminho_arquivo):
            return dict_padrao

        with open(caminho_arquivo, "r", encoding="utf-8") as f:
            dados = json.load(f)

        if not isinstance(dados, dict):
            return dict_padrao

        if dados.get("data") != hoje:
            return dict_padrao

        return {
            "data": hoje,
            "mensagens": max(0, int(dados.get("mensagens", 0))),
            "imagens": max(0, int(dados.get("imagens", 0))),
        }
    except Exception as e:
        logger = obter_logger(tenant_id)
        logger.error(f"Erro ao ler arquivo de uso do dia: {e}", exc_info=True)
        return dict_padrao


def incrementar_uso(tenant_id: str, tipo: str, quantidade: int = 1):
    """Carrega o uso atual, incrementa o contador do 'tipo' ("mensagens" ou "imagens")
    pela 'quantidade' especificada (padrão 1), e salva no arquivo JSON.
    """
    try:
        uso = carregar_uso_do_dia(tenant_id)
        if tipo in uso:
            uso[tipo] = max(0, uso[tipo] + quantidade)
        else:
            uso[tipo] = max(0, quantidade)

        os.makedirs("tenant_data", exist_ok=True)
        caminho_arquivo = os.path.join("tenant_data", f"{tenant_id}_usage.json")

        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            json.dump(uso, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger = obter_logger(tenant_id)
        logger.error(f"Erro ao salvar/incrementar uso do dia ({tipo}): {e}", exc_info=True)


def verificar_limite(tenant_id: str, tipo: str, limite: int, quantidade_necessaria: int = 1) -> bool:
    """Retorna True se o uso atual + quantidade_necessaria for menor ou igual ao limite.
    Retorna False caso o limite diário seja excedido.
    Em caso de erro interno, retorna True para não bloquear o usuário por falha técnica.
    """
    try:
        uso = carregar_uso_do_dia(tenant_id)
        atual = uso.get(tipo, 0)
        permitido = (atual + quantidade_necessaria) <= limite
        if not permitido:
            logger = obter_logger(tenant_id)
            logger.info(f"Limite diário de {tipo} atingido/excedido (solicitado: {atual + quantidade_necessaria}, limite: {limite})")
        return permitido
    except Exception as e:
        logger = obter_logger(tenant_id)
        logger.error(f"Erro ao verificar limite de {tipo}: {e}", exc_info=True)
        return True

