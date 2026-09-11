# -*- coding: utf-8 -*-
"""Validadores da ficha técnica (Fase 11, Task 2).

Todo validador aqui é uma função pura: recebe o dict de `dados` (a forma que `fichas_modelo.py`
descreve) e devolve uma lista de alertas, nunca lança exceção, nunca modifica os dados, nunca
consulta a API. Isso é deliberado -- são exatamente os validadores que o CI consegue exercitar sem
gastar crédito de OpenAI, e são a parte do produto onde "bloquear o usuário por engano" custa mais
caro que "deixar passar um alerta que ele ignora".

Regra do produto (item 18 do prompt do usuário): "o sistema deve mostrar alertas, mas não bloquear
automaticamente informações que sejam legitimamente opcionais." Por isso toda função aqui devolve
alertas informativos -- quem decide o que fazer com eles é a tela de revisão (Task 8).
"""

import re
from typing import List, Optional

import fichas_modelo as fm

SEVERIDADE_ALERTA = "alerta"

# Tolerâncias deliberadamente folgadas: o objetivo é pegar erro grosseiro (composição somando 60%
# ou 140%, custo com uma casa decimal trocada), não perseguir arredondamento de centavo.
TOLERANCIA_COMPOSICAO_PONTOS = 2.0  # em pontos percentuais
TOLERANCIA_CUSTO_REAIS = 0.05

_REGEX_PERCENTUAL = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")

# Campos cuja ausência vale um alerta na revisão -- não impedem salvar/gerar, só chamam atenção.
CAMPOS_ESSENCIAIS = ("ficha.nome", "ficha.ref", "ficha.descricao")


def _alerta(codigo: str, campo: str, mensagem: str) -> dict:
    return {"codigo": codigo, "severidade": SEVERIDADE_ALERTA, "campo": campo, "mensagem": mensagem}


def _extrair_percentuais(texto: Optional[str]) -> List[float]:
    """Lê números seguidos de '%' num texto livre (ex: "95% algodão, 5% elastano" -> [95.0, 5.0]).

    Puramente heurístico -- composição é um campo de texto livre, não estruturado, porque é assim
    que o template .docx real representa (uma única célula "COMPOSIÇÃO" por linha da tabela, não
    uma coluna por fibra). Isso é suficiente para um alerta de revisão; não tenta ser um parser
    exaustivo de todo jeito de escrever percentual em português.
    """
    if not texto:
        return []
    valores = []
    for correspondencia in _REGEX_PERCENTUAL.finditer(texto):
        try:
            valores.append(float(correspondencia.group(1).replace(",", ".")))
        except ValueError:
            continue
    return valores


def validar_composicao(dados: dict) -> List[dict]:
    """Alerta quando os percentuais mencionados na composição de um tecido não somam ~100%.

    Só valida tecidos, não aviamentos: aviamento (linha, botão, zíper) não tem uma expectativa de
    "soma 100%" -- só a composição de tecido tem esse significado (regra 18 do prompt).
    """
    alertas = []
    for indice, tecido in enumerate(dados.get("tecidos", []) or []):
        composicao = fm.valor_de(tecido.get("composicao"))
        percentuais = _extrair_percentuais(composicao)
        if not percentuais:
            continue  # sem percentual escrito -- nada a validar, não é erro
        soma = sum(percentuais)
        if abs(soma - 100.0) > TOLERANCIA_COMPOSICAO_PONTOS:
            alertas.append(_alerta(
                "composicao_nao_soma_100",
                f"tecidos[{indice}].composicao",
                f"A composição do tecido {indice + 1} soma {soma:.1f}%, o esperado é 100%.",
            ))
    return alertas


def validar_custos(dados: dict) -> List[dict]:
    """Alerta quando aviamentos + tecidos + costura/beneficiamento + outros != preço total.

    Cada categoria é {custo, observacao} no schema real (tabela CUSTOS do template tem uma linha
    "OBS.:" própria por categoria) -- só o subcampo "custo" entra na soma.

    Só valida se as 4 categorias E o total estiverem preenchidos -- com qualquer um ausente não
    há como validar com confiança, e o item 7 do prompt já cobre esse caso ("quando algum valor
    não estiver disponível, não inventar... mostrar como não informado").
    """
    custos = dados.get("custos", {}) or {}

    def _custo(nome: str) -> Optional[float]:
        return fm.valor_de((custos.get(nome) or {}).get("custo"))

    aviamentos = _custo("aviamentos")
    tecidos = _custo("tecidos")
    costura = _custo("costura_beneficiamento")
    outros = _custo("outros")
    total = _custo("preco_total")

    if None in (aviamentos, tecidos, costura, outros, total):
        return []

    soma = aviamentos + tecidos + costura + outros
    if abs(soma - total) > TOLERANCIA_CUSTO_REAIS:
        return [_alerta(
            "custos_nao_batem",
            "custos.preco_total.custo",
            f"Aviamentos + tecidos + costura/beneficiamento + outros = R$ {soma:.2f}, "
            f"mas o preço total informado é R$ {total:.2f}.",
        )]
    return []


def validar_grade(dados: dict) -> List[dict]:
    """Alerta sobre tamanho fora da lista conhecida e sobre grade totalmente vazia.

    Valores fora de TAMANHOS_NUMERICOS/TAMANHOS_COMERCIAIS não deveriam existir se os dados vieram
    da extração (o schema usa enum fechado), mas podem existir em dados editados manualmente na
    revisão ou salvos por uma versão anterior do formato -- por isso valida de novo aqui.
    """
    grade = dados.get("grade", {}) or {}
    numericos = fm.valor_de(grade.get("numericos")) or []
    comerciais = fm.valor_de(grade.get("comerciais")) or []
    alertas = []

    invalidos_num = [t for t in numericos if t not in fm.TAMANHOS_NUMERICOS]
    if invalidos_num:
        alertas.append(_alerta(
            "tamanho_numerico_invalido", "grade.numericos",
            f"Tamanho(s) numérico(s) não reconhecido(s): {', '.join(invalidos_num)}.",
        ))

    invalidos_com = [t for t in comerciais if t not in fm.TAMANHOS_COMERCIAIS]
    if invalidos_com:
        alertas.append(_alerta(
            "tamanho_comercial_invalido", "grade.comerciais",
            f"Tamanho(s) comercial(is) não reconhecido(s): {', '.join(invalidos_com)}.",
        ))

    if not numericos and not comerciais:
        alertas.append(_alerta("grade_vazia", "grade", "Nenhum tamanho foi informado na grade."))

    return alertas


def validar_campos_essenciais(dados: dict) -> List[dict]:
    """Alerta sobre campo essencial (ref/nome/descrição) sem informação -- não bloqueia: o
    usuário pode legitimamente ainda não ter definido a referência, por exemplo."""
    alertas = []
    for caminho in CAMPOS_ESSENCIAIS:
        secao, campo = caminho.split(".")
        valor = fm.valor_de((dados.get(secao) or {}).get(campo))
        if not valor:
            alertas.append(_alerta(
                "campo_essencial_ausente", caminho,
                f"Campo essencial '{campo}' não foi informado.",
            ))
    return alertas


def validar_ficha(dados: dict) -> List[dict]:
    """Roda todos os validadores e devolve a lista combinada de alertas, na ordem em que a tela
    de revisão deve mostrá-los: essenciais ausentes primeiro (o que mais precisa de atenção antes
    de gerar um documento), depois inconsistências numéricas."""
    alertas = []
    alertas.extend(validar_campos_essenciais(dados))
    alertas.extend(validar_composicao(dados))
    alertas.extend(validar_custos(dados))
    alertas.extend(validar_grade(dados))
    return alertas
