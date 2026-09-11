# -*- coding: utf-8 -*-
"""Extração estruturada da ficha técnica a partir de texto livre (Fase 11, Task 3).

Usa Structured Outputs da Responses API (`text.format` com `type: json_schema`, `strict: True`)
contra `fichas_modelo.SCHEMA_EXTRACAO` -- não tool-calling. Tool-calling serve para o modelo
*decidir agir* (chamar uma ferramenta ou não); aqui a saída é sempre o mesmo formato fixo, e
`strict: True` é o que garante à força que a resposta bate com o schema (a API rejeita a geração
se ela divergir, em vez de devolver um texto solto que a gente teria que adivinhar como fazer
parse).

Este módulo é só o "tradutor" de texto→JSON. Ele NÃO decide o que é seguro aceitar como
FORNECIDO -- essa é a responsabilidade da Task 4 (verificador de proveniência), que roda depois e
audita/corrige o que a extração devolveu. `extrair_dados()` confia na saída do modelo tal como
vem; a garantia de não-invenção não está aqui, está na camada seguinte.
"""

import json
from typing import Any

import fichas_modelo as fm
from logger_config import obter_logger
from rag_config import OPENAI_TEXT_MODEL

MAX_OUTPUT_TOKENS = 4096

# temperature=0: extração é uma tarefa de leitura, não de criatividade -- o mesmo texto de entrada
# deve produzir a mesma extração todas as vezes, tornando o comportamento auditável.
TEMPERATURA = 0.0

PROMPT_SISTEMA = (
    "Você é um extrator de dados técnicos de moda. Leia a descrição da peça fornecida pelo "
    "usuário e preencha o JSON estruturado com os dados técnicos correspondentes.\n\n"
    "REGRA MAIS IMPORTANTE: nunca invente dado técnico. Para cada campo, marque 'origem' como:\n"
    "- FORNECIDO: o usuário disse isso explicitamente no texto -- copie o trecho exato e completo "
    "em 'trecho', palavra por palavra, sem parafrasear.\n"
    "- INFERIDO: você deduziu a partir de outra informação (ex: 'camisa social' sugere um tipo de "
    "gola comum, mas o usuário não mencionou a gola diretamente).\n"
    "- DESCONHECIDO: não há informação suficiente no texto.\n\n"
    "Nunca marque FORNECIDO para um valor que o usuário não escreveu literalmente. Em especial, "
    "NUNCA invente preço, fornecedor, composição percentual, quantidade, medida ou número de "
    "moldes -- se não estiver no texto, marque DESCONHECIDO e deixe o valor vazio/nulo.\n"
    "Datas: se o usuário não informar uma data, deixe vazio -- não use a data de hoje nem "
    "nenhuma outra data que não esteja escrita no texto.\n"
    "Grade de tamanhos: só marque um tamanho como presente se o usuário mencionar explicitamente "
    "essa grade, ou os tamanhos individuais que a compõem.\n"
    "Cores/beneficiamentos, aviamentos, tecidos, sequência operacional e partes da modelagem são "
    "listas: inclua uma entrada por item mencionado no texto. Se nada foi mencionado para uma "
    "lista, devolva a lista vazia -- não invente itens de exemplo."
)


def extrair_dados(client: Any, texto: str, tenant_id: str) -> dict:
    """Extrai um dict no formato de `fichas_modelo.dados_vazios()` a partir de texto livre.

    Nunca lança exceção: em qualquer falha (chamada de API, parse do JSON, formato inesperado),
    devolve `fichas_modelo.dados_vazios()`. Uma ficha vazia é sempre um resultado seguro -- o
    usuário revisa e preenche do zero na tela de revisão (Task 8) -- nunca um erro que trava o
    fluxo.
    """
    logger = obter_logger(tenant_id)

    if not texto or not isinstance(texto, str) or not texto.strip():
        return fm.dados_vazios()

    try:
        resposta = client.responses.create(
            model=OPENAI_TEXT_MODEL,
            instructions=PROMPT_SISTEMA,
            input=[{"role": "user", "content": texto}],
            temperature=TEMPERATURA,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ficha_tecnica",
                    "schema": fm.SCHEMA_EXTRACAO,
                    "strict": True,
                }
            },
        )
    except Exception as e:
        logger.error(f"Falha ao chamar a extração estruturada da ficha: {e}", exc_info=True)
        return fm.dados_vazios()

    texto_saida = getattr(resposta, "output_text", None)
    try:
        dados = json.loads(texto_saida)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"Resposta da extração não é JSON válido: {e}", exc_info=True)
        return fm.dados_vazios()

    if not isinstance(dados, dict):
        logger.error("Resposta da extração não é um objeto JSON (dict).")
        return fm.dados_vazios()

    return dados
