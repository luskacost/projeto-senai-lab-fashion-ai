# -*- coding: utf-8 -*-
"""Módulo de controle e rastreamento de limite de uso por tenant."""

import os
import json
from datetime import datetime
from filelock import FileLock, Timeout
from logger_config import obter_logger


class ErroLeituraUso(Exception):
    """Levantado só para falhas REAIS de leitura do contador (arquivo corrompido, erro de I/O) --
    nunca para "arquivo ainda não existe" ou "é um novo dia", que são o estado vazio normal e
    devolvem o contador zerado sem erro nenhum (ver `_carregar_uso_do_dia_estrito`)."""

# Timeout curto (Fase 9, Bloco D): antes, ler+incrementar o contador de uso era um
# read-modify-write sem nenhum lock -- duas requisições concorrentes podiam ler o mesmo valor
# inicial e cada uma escrever "+1" por cima da outra, perdendo um incremento (e permitindo passar
# do limite diário configurado). O lock é por tenant (um arquivo .lock ao lado do .json de uso).
TIMEOUT_LOCK_SEGUNDOS = 5


def _caminho_lock_uso(tenant_id: str) -> str:
    return os.path.join("tenant_data", f"{tenant_id}_usage.json.lock")


def _carregar_uso_do_dia_estrito(tenant_id: str) -> dict:
    """Lê o arquivo tenant_data/{tenant_id}_usage.json.

    Devolve o contador zerado, sem erro, só nos dois casos que são o estado vazio NORMAL: arquivo
    ainda não existe (primeiro uso do dia) ou a data salva é de um dia anterior (virou o dia).
    Qualquer outro problema de leitura (JSON corrompido, conteúdo que não é um objeto, erro de
    I/O) levanta `ErroLeituraUso` -- não deixa o chamador confundir "nunca usou hoje" com "não
    consigo saber se já usou hoje" (Fase 14, Bloco S, Task 3; ver `verificar_limite` abaixo).

    Genérico em "tipo" (Fase 10, Task 8): preserva qualquer contador numérico salvo no arquivo,
    não só "mensagens"/"imagens" -- antes daquela correção, a função reconstruía o dict retornado
    com só essas duas chaves hardcoded, descartando silenciosamente qualquer outro tipo salvo
    (ex: "buscas_web"). Na prática isso fazia incrementar_uso() "esquecer" o valor acumulado de um
    tipo novo a cada leitura seguinte -- o incremento parecia funcionar (a chave existia no dict
    em memória, era salva no arquivo), mas a próxima leitura descartava o que estava no disco e
    via o contador voltar a não existir, zerando-o de novo em vez de acumular.
    """
    hoje = datetime.now().strftime('%Y-%m-%d')
    dict_padrao = {"data": hoje, "mensagens": 0, "imagens": 0}

    caminho_arquivo = os.path.join("tenant_data", f"{tenant_id}_usage.json")
    if not os.path.exists(caminho_arquivo):
        return dict_padrao

    try:
        with open(caminho_arquivo, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception as e:
        raise ErroLeituraUso(f"Arquivo de uso corrompido ou ilegível: {e}") from e

    if not isinstance(dados, dict):
        raise ErroLeituraUso("Arquivo de uso não contém um objeto JSON válido.")

    if dados.get("data") != hoje:
        return dict_padrao  # virou o dia -- reset normal, não é falha

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


def carregar_uso_do_dia(tenant_id: str) -> dict:
    """Versão tolerante de `_carregar_uso_do_dia_estrito`, para exibição de uso (nunca para
    decidir se um limite foi excedido -- isso é `verificar_limite`, que precisa saber distinguir
    "zero de verdade" de "não consegui ler"). Qualquer erro de leitura vira um contador zerado
    (comportamento de sempre, preservado para quem só quer mostrar "uso de hoje" na tela)."""
    try:
        return _carregar_uso_do_dia_estrito(tenant_id)
    except ErroLeituraUso as e:
        logger = obter_logger(tenant_id)
        logger.error(f"Erro ao ler arquivo de uso do dia: {e}", exc_info=True)
        return {"data": datetime.now().strftime('%Y-%m-%d'), "mensagens": 0, "imagens": 0}


MAX_TENTATIVAS_INCREMENTO = 3  # Fase 14, Bloco S, Task 3 -- ver nota abaixo


def incrementar_uso(tenant_id: str, tipo: str, quantidade: int = 1):
    """Carrega o uso atual, incrementa o contador do 'tipo' (qualquer string -- "mensagens",
    "imagens", "buscas_web", ou um tipo novo futuro) pela 'quantidade' especificada (padrão 1),
    e salva no arquivo JSON.

    Todo o ciclo leitura-modificação-escrita roda dentro de um FileLock por tenant, para que
    duas requisições concorrentes não leiam o mesmo valor inicial e cada uma sobrescreva a
    escrita da outra (perdendo um incremento e potencialmente deixando passar do limite diário).

    Tenta até `MAX_TENTATIVAS_INCREMENTO` vezes antes de desistir (Fase 14, Bloco S, Task 3):
    antes, uma única tentativa que batesse no timeout descartava o incremento em silêncio -- sob
    contenção momentânea (várias requisições no mesmo segundo), o uso real crescia sem que o
    contador refletisse isso, e `verificar_limite` continuava liberando acima do limite
    configurado. Chamado sempre DEPOIS da ação cobrada (mensagem enviada, imagem já gerada), então
    não há o que desfazer se falhar -- só reduzir a chance real de perder o incremento.
    """
    os.makedirs("tenant_data", exist_ok=True)
    for _tentativa in range(MAX_TENTATIVAS_INCREMENTO):
        try:
            with FileLock(_caminho_lock_uso(tenant_id), timeout=TIMEOUT_LOCK_SEGUNDOS):
                uso = carregar_uso_do_dia(tenant_id)
                if tipo in uso:
                    uso[tipo] = max(0, uso[tipo] + quantidade)
                else:
                    uso[tipo] = max(0, quantidade)

                caminho_arquivo = os.path.join("tenant_data", f"{tenant_id}_usage.json")
                with open(caminho_arquivo, "w", encoding="utf-8") as f:
                    json.dump(uso, f, ensure_ascii=False, indent=2)
            return
        except Timeout:
            continue
        except Exception as e:
            logger = obter_logger(tenant_id)
            logger.error(f"Erro ao salvar/incrementar uso do dia ({tipo}): {e}", exc_info=True)
            return

    logger = obter_logger(tenant_id)
    logger.error(
        f"Timeout ao adquirir lock de uso ({tipo}) após {MAX_TENTATIVAS_INCREMENTO} tentativas -- "
        "incremento descartado. Uso real deste tenant pode estar subcontado até a próxima "
        "chamada bem-sucedida."
    )


def verificar_limite(tenant_id: str, tipo: str, limite: int, quantidade_necessaria: int = 1) -> bool:
    """Retorna True se o uso atual + quantidade_necessaria for menor ou igual ao limite.
    Retorna False caso o limite diário seja excedido.

    Fail-CLOSED (Fase 14, Bloco S, Task 3) quando o contador não pode ser lido de verdade --
    antes disso, qualquer erro de leitura liberava o acesso (fail-open): um arquivo de uso
    corrompido virava licença ilimitada até alguém notar o erro no log, o oposto do que um
    controle de limite diário deveria garantir. O pior efeito colateral de negar por padrão é um
    usuário legítimo esperar até a próxima virada de dia ou um admin corrigir o arquivo -- nunca
    gasto sem controle.
    """
    try:
        uso = _carregar_uso_do_dia_estrito(tenant_id)
    except ErroLeituraUso as e:
        logger = obter_logger(tenant_id)
        logger.error(
            f"Erro ao verificar limite de {tipo} -- acesso NEGADO até o arquivo de uso ser "
            f"corrigido ou virar o dia (fail-closed, limite diário não verificado nesta chamada): {e}",
            exc_info=True
        )
        return False

    atual = uso.get(tipo, 0)
    permitido = (atual + quantidade_necessaria) <= limite
    if not permitido:
        logger = obter_logger(tenant_id)
        logger.info(f"Limite diário de {tipo} atingido/excedido (solicitado: {atual + quantidade_necessaria}, limite: {limite})")
    return permitido

