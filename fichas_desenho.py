# -*- coding: utf-8 -*-
"""Geração e armazenamento do desenho técnico da ficha (Fase 11, Task 15).

## Por que não reaproveitar geracao_imagem.chamar_api_geracao_imagem() como está

Aquela função devolve uma data URI base64 (`data:image/png;base64,...`), pronta pro `<img src>`
do chat -- e nunca grava nada em disco, porque no chat a imagem só precisa existir durante aquela
resposta. O desenho técnico da ficha é diferente: precisa ser um **arquivo persistente**, porque:

- sobrevive a um recarregamento de página (o chat não precisa disso -- a imagem já teria sumido
  do histórico de qualquer jeito);
- entra no `.docx` via `InlineImage` (Task 18), que exige um caminho de arquivo no disco, não uma
  string base64 solta em memória;
- terá várias versões lado a lado (v1, v2, v3 -- Task 16), cada uma seu próprio arquivo.

Por isso esta função devolve bytes crus, não a data URI: evita decodificar/recodificar base64 sem
necessidade num caminho cujo destino final é sempre "escrever num arquivo".

## O que este módulo NÃO faz (de propósito)

Não modera o prompt, não decide versão, não muda status da ficha, não incrementa cota de uso. Essa
orquestração é da Task 16/17 -- este módulo é só a camada de geração + persistência + leitura, o
mesmo tipo de camada fina que `fichas_pdf.py` é para a conversão via LibreOffice. O handler do
chat (`agente_ferramentas._handler_gerar_imagem_croqui`/`_handler_gerar_ficha_tecnica`) continua
usando `geracao_imagem.chamar_api_geracao_imagem()` sem nenhuma mudança.
"""

import base64
import os
from typing import Any, Optional

import fichas_repo
from logger_config import obter_logger

PREFIXO_ARQUIVO = "desenho_v"


def gerar_imagem_desenho(
    client: Any, prompt_visual: str, tenant_id: str, tamanho: str = "1024x1536"
) -> Optional[bytes]:
    """Gera o desenho via gpt-image-1 e devolve os bytes crus do PNG -- ou None se a geração
    falhar (rejeição do filtro de conteúdo da própria OpenAI, erro de rede/quota).

    Mesmo modelo e parâmetros de geracao_imagem.chamar_api_geracao_imagem(); a única diferença é
    a forma do retorno (bytes prontos para `open(..., "wb")`, não uma data URI).

    A moderação do prompt (moderacao.validar_prompt_imagem) é responsabilidade de quem chama esta
    função, não dela -- mesma separação que a rota /chat/croqui/confirmar já faz hoje.
    """
    try:
        resposta = client.images.generate(
            model="gpt-image-1",
            prompt=prompt_visual,
            size=tamanho,
            n=1,
        )
        return base64.b64decode(resposta.data[0].b64_json)
    except Exception as e:
        obter_logger(tenant_id).error(f"Falha ao gerar desenho técnico via gpt-image-1: {e}", exc_info=True)
        return None


def _nome_arquivo(versao: int) -> str:
    if versao < 1:
        raise ValueError(f"versão de desenho inválida: {versao} (precisa ser >= 1)")
    return f"{PREFIXO_ARQUIVO}{versao}.png"


def salvar_desenho(tenant_id: str, ficha_id: str, versao: int, conteudo: bytes) -> str:
    """Grava os bytes do desenho na pasta da própria ficha, como desenho_v{versao}.png.

    Devolve o caminho salvo. Cada versão é um arquivo próprio -- nunca sobrescreve uma versão
    anterior, o que é o que permite comparar v_n com v_{n-1} na revisão (Task 17).
    """
    caminho = fichas_repo.caminho_arquivo_da_ficha(tenant_id, ficha_id, _nome_arquivo(versao))
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "wb") as f:
        f.write(conteudo)
    return caminho


def caminho_desenho(tenant_id: str, ficha_id: str, versao: int) -> Optional[str]:
    """Caminho do arquivo de uma versão do desenho, ou None se ela não existir em disco.

    Levanta ValueError para versão inválida (< 1) -- propositalmente diferente de "não
    encontrada": o chamador HTTP (Task 15) distingue os dois como 400 e 404.
    """
    caminho = fichas_repo.caminho_arquivo_da_ficha(tenant_id, ficha_id, _nome_arquivo(versao))
    return caminho if os.path.exists(caminho) else None
