# -*- coding: utf-8 -*-
"""Modelo de dados da ficha técnica de moda (Fase 11, Task 1).

Este módulo é o *contrato* do qual todo o resto da Fase 11 depende: a extração estruturada
(Task 3), os validadores (Task 2), o verificador de proveniência (Task 4), os placeholders do
template .docx (Task 10) e o formulário de revisão do frontend (Task 8). Por isso ele vem antes
de tudo -- inclusive antes do template .docx chegar: renomear um campo depois que os placeholders
do Word já existirem significa mexer no documento do usuário, não só no código.

## Por que todo campo é um objeto {valor, origem, trecho}

A regra mais importante do produto é que a IA **não pode inventar** dado técnico (preço,
fornecedor, composição, medida, número de moldes). Instrução de prompt não garante isso -- modelo
de linguagem preenche lacuna com o que é plausível, é o comportamento default dele.

A garantia real é estrutural: o schema obriga o modelo a declarar, para cada valor, de onde ele
veio (`origem`) e qual trecho do texto do usuário o sustenta (`trecho`). Isso permite que a Task 4
faça uma verificação *determinística* (o trecho é mesmo substring do que o usuário escreveu?) e
zere pelo código qualquer campo de CAMPOS_NAO_INFERIVEIS que não seja FORNECIDO. O prompt vira
reforço, não a trava.

## Por que "sem informação" é string vazia, nunca campo ausente

Structured Outputs da OpenAI em modo `strict` exige que *toda* propriedade esteja em `required` e
que todo objeto tenha `additionalProperties: false`. Não existe campo opcional. Então a ausência
de informação é representada por valor vazio ("" para texto, null para número) com
`origem: DESCONHECIDO` -- e não pela omissão da chave.
"""

from typing import Any

# --- Proveniência -----------------------------------------------------------------------------

ORIGEM_FORNECIDO = "FORNECIDO"      # dito explicitamente pelo usuário
ORIGEM_OBSERVADO = "OBSERVADO"      # lido de imagem/documento anexado (ainda não usado; Bloco C)
ORIGEM_INFERIDO = "INFERIDO"        # deduzido pela IA a partir de outra informação
ORIGEM_DESCONHECIDO = "DESCONHECIDO"  # não disponível

ORIGENS = (ORIGEM_FORNECIDO, ORIGEM_OBSERVADO, ORIGEM_INFERIDO, ORIGEM_DESCONHECIDO)

# Campos que afetam produção/custo e por isso NÃO podem ser inferidos: se a origem não for
# FORNECIDO (ou OBSERVADO), a Task 4 zera o valor pelo código. Um preço inventado vira pedido de
# compra errado; uma composição inventada vira lote de tecido errado.
# Caminho usa "[]" para indicar item de lista (ex: todos os aviamentos).
CAMPOS_NAO_INFERIVEIS = (
    "ficha.data",
    "ficha.designer",
    "aviamentos[].composicao",
    "aviamentos[].quantidade",
    "aviamentos[].fornecedor",
    "aviamentos[].preco",
    "tecidos[].composicao",
    "tecidos[].quantidade",
    "tecidos[].largura",
    "tecidos[].fornecedor",
    "tecidos[].preco",
    "custos.aviamentos",
    "custos.tecidos",
    "custos.costura_beneficiamento",
    "custos.preco_total",
    "sequencia_operacional[].maquinas",
    "modelagem.modelista",
    "modelagem.numero_moldes",
)

# --- Grade de tamanhos ------------------------------------------------------------------------

TAMANHOS_NUMERICOS = ("34", "36", "38", "40", "42", "44", "46", "48", "50", "52", "54", "56")
TAMANHOS_COMERCIAIS = ("PP", "P", "M", "G", "GG", "XG")

# --- Status da ficha --------------------------------------------------------------------------

STATUS_RASCUNHO = "RASCUNHO"
STATUS_EM_REVISAO = "EM_REVISAO"
STATUS_DESENHO_GERADO = "DESENHO_GERADO"
STATUS_AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO"
STATUS_APROVADA = "APROVADA"
STATUS_DOCUMENTO_GERADO = "DOCUMENTO_GERADO"

STATUS_FICHA = (
    STATUS_RASCUNHO,
    STATUS_EM_REVISAO,
    STATUS_DESENHO_GERADO,
    STATUS_AGUARDANDO_APROVACAO,
    STATUS_APROVADA,
    STATUS_DOCUMENTO_GERADO,
)

# Status de cada versão do desenho técnico. Nenhum desenho é aprovado automaticamente: só a
# versão explicitamente aprovada pelo usuário entra no documento final.
DESENHO_GERADO = "gerado"
DESENHO_AGUARDANDO_APROVACAO = "aguardando_aprovacao"
DESENHO_APROVADO = "aprovado"


# --- Construtores de schema -------------------------------------------------------------------

def _bloco_proveniencia(descricao_valor: str, schema_valor: dict) -> dict:
    """Envolve um valor no trio {valor, origem, trecho} exigido de todo campo extraído.

    As descrições de `origem` e `trecho` são deliberadamente curtas: elas se repetiriam em cada
    um dos ~30 campos do schema, e o schema inteiro viaja em toda chamada de extração. A
    explicação completa das regras de proveniência fica no prompt de sistema da extração
    (Task 3), dita uma vez só.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["valor", "origem", "trecho"],
        "properties": {
            "valor": {**schema_valor, "description": descricao_valor},
            "origem": {"type": "string", "enum": list(ORIGENS)},
            "trecho": {"type": "string", "description": "Trecho literal do texto do usuário que sustenta o valor."},
        },
    }


def campo_texto(descricao: str) -> dict:
    return _bloco_proveniencia(descricao, {"type": "string"})


def campo_numero(descricao: str) -> dict:
    """Número que pode estar ausente. Em strict mode a ausência se expressa por união com null --
    string vazia não serve, o decodificador rejeitaria."""
    return _bloco_proveniencia(descricao, {"type": ["number", "null"]})


def campo_lista_enum(valores: tuple, descricao: str) -> dict:
    return _bloco_proveniencia(descricao, {"type": "array", "items": {"type": "string", "enum": list(valores)}})


def _objeto(propriedades: dict) -> dict:
    """Objeto no formato exigido pelo strict mode: additionalProperties False e todas as
    propriedades obrigatórias."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(propriedades.keys()),
        "properties": propriedades,
    }


def _lista_de(propriedades: dict, descricao: str) -> dict:
    return {"type": "array", "description": descricao, "items": _objeto(propriedades)}


# --- Schema de extração -----------------------------------------------------------------------
# O que a IA deve produzir a partir do texto livre. Não inclui estado do sistema (id, status,
# desenho, documentos gerados) -- isso não se extrai de texto, é responsabilidade do repositório.

_PROPRIEDADES_AVIAMENTO = {
    "descricao": campo_texto("Descrição do aviamento (ex: botão, zíper, etiqueta, linha)."),
    "composicao": campo_texto("Composição/material do aviamento."),
    "cor": campo_texto("Cor do aviamento."),
    "quantidade": campo_numero("Quantidade usada na peça."),
    "fornecedor": campo_texto("Nome do fornecedor."),
    "preco": campo_numero("Preço unitário em reais."),
}

_PROPRIEDADES_TECIDO = {
    "descricao": campo_texto("Descrição do tecido (ex: malha, tricoline, sarja)."),
    "composicao": campo_texto("Composição do tecido (ex: 95% algodão, 5% elastano)."),
    "cor": campo_texto("Cor do tecido."),
    "quantidade": campo_numero("Consumo em metros."),
    "largura": campo_numero("Largura do tecido em metros."),
    "fornecedor": campo_texto("Nome do fornecedor."),
    "preco": campo_numero("Preço por metro em reais."),
}

_PROPRIEDADES_OPERACAO = {
    "descricao": campo_texto("Descrição da operação (ex: fechar ombros, aplicar gola)."),
    "maquinas": campo_texto("Máquina(s) usada(s) na operação (ex: overloque, reta, galoneira)."),
}

SCHEMA_EXTRACAO = _objeto({
    "ficha": _objeto({
        "ref": campo_texto("Código de referência da peça."),
        "nome": campo_texto("Nome da peça."),
        "colecao": campo_texto("Coleção a que a peça pertence."),
        "descricao": campo_texto("Descrição da peça conforme o usuário a descreveu."),
        "designer": campo_texto("Nome do designer responsável."),
        "data": campo_texto("Data da ficha, no formato DD/MM/AAAA."),
        "tecnica": campo_texto("Técnica empregada na peça."),
        "empresa": campo_texto("Empresa/marca da peça."),
    }),
    "grade": _objeto({
        "numericos": campo_lista_enum(TAMANHOS_NUMERICOS, "Tamanhos numéricos que a peça terá."),
        "comerciais": campo_lista_enum(TAMANHOS_COMERCIAIS, "Tamanhos comerciais que a peça terá."),
    }),
    "aviamentos": _lista_de(_PROPRIEDADES_AVIAMENTO, "Aviamentos da peça. Lista vazia se nenhum foi informado."),
    "tecidos": _lista_de(_PROPRIEDADES_TECIDO, "Tecidos da peça. Lista vazia se nenhum foi informado."),
    "custos": _objeto({
        "aviamentos": campo_numero("Custo total de aviamentos em reais."),
        "tecidos": campo_numero("Custo total de tecidos em reais."),
        "costura_beneficiamento": campo_numero("Custo de costura e beneficiamento em reais."),
        "preco_total": campo_numero("Preço total da peça em reais."),
    }),
    "sequencia_operacional": _lista_de(
        _PROPRIEDADES_OPERACAO,
        "Sequência de operações de costura, na ordem de execução. Lista vazia se não houver "
        "informação suficiente sobre a construção da peça.",
    ),
    "modelagem": _objeto({
        "modelista": campo_texto("Nome do modelista responsável."),
        "numero_moldes": campo_numero("Quantidade de moldes da peça."),
        "partes_componentes": campo_texto("Partes componentes da modelagem."),
        "corte": campo_texto("Observações sobre o corte."),
    }),
})


# --- Valores vazios ---------------------------------------------------------------------------

def _campo_vazio(valor_padrao: Any) -> dict:
    return {"valor": valor_padrao, "origem": ORIGEM_DESCONHECIDO, "trecho": ""}


def campo_texto_vazio() -> dict:
    return _campo_vazio("")


def campo_numero_vazio() -> dict:
    return _campo_vazio(None)


def aviamento_vazio() -> dict:
    return {
        "descricao": campo_texto_vazio(),
        "composicao": campo_texto_vazio(),
        "cor": campo_texto_vazio(),
        "quantidade": campo_numero_vazio(),
        "fornecedor": campo_texto_vazio(),
        "preco": campo_numero_vazio(),
    }


def tecido_vazio() -> dict:
    return {
        "descricao": campo_texto_vazio(),
        "composicao": campo_texto_vazio(),
        "cor": campo_texto_vazio(),
        "quantidade": campo_numero_vazio(),
        "largura": campo_numero_vazio(),
        "fornecedor": campo_texto_vazio(),
        "preco": campo_numero_vazio(),
    }


def operacao_vazia() -> dict:
    return {"descricao": campo_texto_vazio(), "maquinas": campo_texto_vazio()}


def dados_vazios() -> dict:
    """Dados extraíveis zerados -- mesma forma que SCHEMA_EXTRACAO descreve."""
    return {
        "ficha": {
            "ref": campo_texto_vazio(),
            "nome": campo_texto_vazio(),
            "colecao": campo_texto_vazio(),
            "descricao": campo_texto_vazio(),
            "designer": campo_texto_vazio(),
            "data": campo_texto_vazio(),
            "tecnica": campo_texto_vazio(),
            "empresa": campo_texto_vazio(),
        },
        "grade": {"numericos": _campo_vazio([]), "comerciais": _campo_vazio([])},
        "aviamentos": [],
        "tecidos": [],
        "custos": {
            "aviamentos": campo_numero_vazio(),
            "tecidos": campo_numero_vazio(),
            "costura_beneficiamento": campo_numero_vazio(),
            "preco_total": campo_numero_vazio(),
        },
        "sequencia_operacional": [],
        "modelagem": {
            "modelista": campo_texto_vazio(),
            "numero_moldes": campo_numero_vazio(),
            "partes_componentes": campo_texto_vazio(),
            "corte": campo_texto_vazio(),
        },
    }


def ficha_vazia() -> dict:
    """Documento completo da ficha, como é persistido em disco.

    Deliberadamente puro (sem uuid nem datetime): `id` e timestamps são preenchidos pelo
    repositório (Task 5), o que mantém este módulo determinístico e trivial de testar.
    """
    return {
        "id": "",
        "status": STATUS_RASCUNHO,
        "criado_em": "",
        "atualizado_em": "",
        "texto_origem": "",
        "dados": dados_vazios(),
        "desenho": {
            "solicitado": False,
            "versoes": [],
            "versao_aprovada": None,
        },
        "documentos": {"docx": "", "pdf": "", "gerado_em": ""},
    }


# --- Acesso a campos --------------------------------------------------------------------------

def valor_de(campo: Any) -> Any:
    """Extrai o valor de um campo com proveniência, tolerando campo malformado/ausente.

    Usado por validadores, render do .docx e afins, que se importam com o valor e não com a
    proveniência -- e que não podem quebrar se o dict vier de um arquivo salvo por uma versão
    anterior do formato.
    """
    if isinstance(campo, dict):
        return campo.get("valor")
    return None


def origem_de(campo: Any) -> str:
    if isinstance(campo, dict):
        origem = campo.get("origem")
        if origem in ORIGENS:
            return origem
    return ORIGEM_DESCONHECIDO
