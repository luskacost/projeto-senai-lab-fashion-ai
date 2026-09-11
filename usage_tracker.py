# -*- coding: utf-8 -*-
"""Módulo de controle e rastreamento de limite de uso por tenant."""

import os
import json
from datetime import datetime
from filelock import FileLock, Timeout
from logger_config import obter_logger

# Timeout curto (Fase 9, Bloco D): antes, ler+incrementar o contador de uso era um
# read-modify-write sem nenhum lock -- duas requisições concorrentes podiam ler o mesmo valor
# inicial e cada uma escrever "+1" por cima da outra, perdendo um incremento (e permitindo passar
# do limite diário configurado). O lock é por tenant (um arquivo .lock ao lado do .json de uso).
TIMEOUT_LOCK_SEGUNDOS = 5


def _caminho_lock_uso(tenant_id: str) -> str:
    return os.path.join("tenant_data", f"{tenant_id}_usage.json.lock")


def carregar_uso_do_dia(tenant_id: str) -> dict:
    """Lê o arquivo tenant_data/{tenant_id}_usage.json.

    Se o arquivo não existir, for inválido ou tiver data diferente de hoje (YYYY-MM-DD),
    retorna um dicionário zerado com pelo menos {"data": "AAAA-MM-DD", "mensagens": 0, "imagens": 0}
    sem modificar o disco.

    Genérico em "tipo" (Fase 10, Task 8): preserva qualquer contador numérico salvo no arquivo,
    não só "mensagens"/"imagens" -- antes desta correção, a função reconstruía o dict retornado
    com só essas duas chaves hardcoded, descartando silenciosamente qualquer outro tipo salvo
    (ex: "buscas_web", introduzido nesta mesma task). Na prática isso fazia incrementar_uso()
    "esquecer" o valor acumulado de um tipo novo a cada leitura seguinte -- o incremento parecia
    funcionar (a chave existia no dict em memória, era salva no arquivo), mas a próxima leitura
    descartava o que estava no disco e via o contador voltar a não existir, zerando-o de novo em
    vez de acumular.
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

        uso = {"data": hoje}
        for chave, valor in dados.items():
            if chave == "data":
                continue
            try:
                uso[chave] = max(0, int(valor))
            except (TypeError, ValueError):
                continue  # contador corrompido/não numérico -- ignora em vez de propagar erro
        uso.setdefault("mensagens", 0)
        uso.setdefault("imagens", 0)
        return uso
    except Exception as e:
        logger = obter_logger(tenant_id)
        logger.error(f"Erro ao ler arquivo de uso do dia: {e}", exc_info=True)
        return dict_padrao


def incrementar_uso(tenant_id: str, tipo: str, quantidade: int = 1):
    """Carrega o uso atual, incrementa o contador do 'tipo' (qualquer string -- "mensagens",
    "imagens", "buscas_web", ou um tipo novo futuro) pela 'quantidade' especificada (padrão 1),
    e salva no arquivo JSON.

    Todo o ciclo leitura-modificação-escrita roda dentro de um FileLock por tenant, para que
    duas requisições concorrentes não leiam o mesmo valor inicial e cada uma sobrescreva a
    escrita da outra (perdendo um incremento e potencialmente deixando passar do limite diário).
    """
    try:
        os.makedirs("tenant_data", exist_ok=True)
        with FileLock(_caminho_lock_uso(tenant_id), timeout=TIMEOUT_LOCK_SEGUNDOS):
            uso = carregar_uso_do_dia(tenant_id)
            if tipo in uso:
                uso[tipo] = max(0, uso[tipo] + quantidade)
            else:
                uso[tipo] = max(0, quantidade)

            caminho_arquivo = os.path.join("tenant_data", f"{tenant_id}_usage.json")
            with open(caminho_arquivo, "w", encoding="utf-8") as f:
                json.dump(uso, f, ensure_ascii=False, indent=2)
    except Timeout:
        logger = obter_logger(tenant_id)
        logger.error(f"Timeout ao adquirir lock de uso ({tipo}) -- incremento descartado para não travar a requisição.")
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
        # Fail-open deliberado (não travar o usuário por falha técnica transitória) -- mas isso
        # significa que o limite diário NÃO foi de fato verificado nesta chamada. A mensagem
        # deixa esse efeito colateral explícito no log, em vez de um erro genérico que passaria
        # despercebido em qualquer ferramenta de monitoramento de log.
        logger.error(
            f"Erro ao verificar limite de {tipo} -- acesso liberado apesar do erro (fail-open, "
            f"limite diário não verificado nesta chamada): {e}",
            exc_info=True
        )
        return True

