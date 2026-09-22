# -*- coding: utf-8 -*-
"""Preço sugerido a partir dos custos da ficha (Fase 14, Bloco P, Task 18).

Função pura e determinística, no mesmo espírito de `fichas_validacao.py`: recebe dicts, devolve um
dict, nunca lança exceção, nunca modifica a entrada, nunca consulta a API. O resultado **nunca é
persistido** -- é recalculado a cada leitura da ficha (ver `api/main.py:_ficha_com_alertas`), pelo
mesmo motivo que os alertas também são: um número calculado, se fosse gravado em `dados` com uma
`origem`, viraria um dado com cara de "informado pelo usuário" -- exatamente o que a regra de
não-invenção do projeto proíbe. Preço sugerido é uma conta sobre o que já está na ficha, não um
fato novo sobre a peça.

## Markup divisor, não multiplicador

    preco = custo / (1 - (imposto% + comissao% + margem%) / 100)

Imposto, comissão e margem incidem sobre o **preço de venda**, não sobre o custo -- então somar
percentuais em cima do custo (markup multiplicador, `custo * 1,45`) entrega menos do que a margem
pedida. Exemplo com custo R$ 100 e 45% somados: o multiplicador dá R$ 145,00, dos quais 45% (R$
65,25) vão embora, sobrando R$ 79,75 -- menos que o próprio custo. O divisor dá R$ 181,82, dos
quais 45% (R$ 81,82) saem, sobrando exatamente os R$ 100 de custo.

## Decimal, não float

`Decimal` com `ROUND_HALF_UP` em vez de `float` puro: a diferença aparece no centavo, e centavo
aqui não é detalhe cosmético -- `fichas_validacao.TOLERANCIA_CUSTO_REAIS` é R$ 0,05, então um erro
de arredondamento de R$ 0,01 propagado para o preço total cabe dentro da tolerância e passa
despercebido pelo alerta de "custos não batem".
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import fichas_modelo as fm

# As 4 categorias que somam o custo de produção. "preco_total" fica FORA de propósito: ele é o
# preço que a pessoa decidiu cobrar, não um custo -- é justamente o número que o preço sugerido
# existe para ajudar a decidir (e que o botão "usar como preço total" da UI preenche, por ação
# humana explícita, nunca automaticamente).
CATEGORIAS_DE_CUSTO = ("aviamentos", "tecidos", "costura_beneficiamento", "outros")

NOMES_DOS_PARAMETROS = ("imposto_percentual", "comissao_percentual", "margem_lucro_percentual")

CENTAVO = Decimal("0.01")


def _para_decimal(valor: Any) -> Optional[Decimal]:
    """Converte para Decimal via str (nunca via float direto: Decimal(0.1) carrega o erro binário
    do float inteiro, Decimal("0.1") não). Devolve None para qualquer coisa que não seja um número
    finito -- incluindo bool, que em Python é int e passaria por engano."""
    if isinstance(valor, bool) or valor is None:
        return None
    if not isinstance(valor, (int, float, str, Decimal)):
        return None
    try:
        convertido = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return convertido if convertido.is_finite() else None


def _arredondar(valor: Decimal) -> float:
    return float(valor.quantize(CENTAVO, rounding=ROUND_HALF_UP))


def parametros_padrao() -> Dict[str, float]:
    """Todos zerados: sem configuração, o preço sugerido é igual ao custo -- um resultado correto e
    honesto ("você não pediu margem nenhuma"), não um palpite. Os valores de verdade vêm do tenant
    (Task 19), que é quem sabe a carga tributária e a comissão praticadas."""
    return {nome: 0.0 for nome in NOMES_DOS_PARAMETROS}


def _normalizar_parametros(parametros: Optional[dict]) -> tuple:
    """Devolve (parametros_normalizados, motivo_de_erro). Ausente vira 0,0 (é uma escolha válida:
    "não cobro comissão"); negativo ou não-numérico é erro, não um zero implícito -- um percentual
    inválido silenciosamente virando zero entregaria um preço abaixo do pretendido sem aviso."""
    entrada = parametros or {}
    normalizados: Dict[str, float] = {}

    for nome in NOMES_DOS_PARAMETROS:
        bruto = entrada.get(nome)
        if bruto is None or bruto == "":
            normalizados[nome] = 0.0
            continue
        convertido = _para_decimal(bruto)
        if convertido is None:
            return {}, f"O parâmetro '{nome}' não é um número válido."
        if convertido < 0:
            return {}, f"O parâmetro '{nome}' não pode ser negativo."
        normalizados[nome] = float(convertido)

    return normalizados, ""


def _somar_custos(dados: dict) -> tuple:
    """Devolve (soma, informadas, ausentes). Categoria ausente NÃO vira zero silencioso: entra em
    `ausentes` para a UI mostrar sobre quantas categorias o cálculo foi feito -- somar só o que foi
    informado e apresentar o resultado como se fosse o custo completo esconderia o buraco."""
    custos_brutos = (dados or {}).get("custos") if isinstance(dados, dict) else None
    custos = custos_brutos if isinstance(custos_brutos, dict) else {}
    soma = Decimal("0")
    informadas: Dict[str, float] = {}
    ausentes: List[str] = []

    for nome in CATEGORIAS_DE_CUSTO:
        categoria = custos.get(nome)
        campo_custo = categoria.get("custo") if isinstance(categoria, dict) else None
        valor = _para_decimal(fm.valor_de(campo_custo))
        if valor is None:
            ausentes.append(nome)
            continue
        soma += valor
        informadas[nome] = float(valor)

    return soma, informadas, ausentes


def _nao_calculavel(motivo: str, parametros: Dict[str, float], informadas=None, ausentes=None) -> Dict[str, Any]:
    return {
        "calculavel": False,
        "motivo": motivo,
        "preco_sugerido": None,
        "custo_total": None,
        "categorias_informadas": informadas or {},
        "categorias_ausentes": list(ausentes if ausentes is not None else CATEGORIAS_DE_CUSTO),
        "parametros": parametros or parametros_padrao(),
        "percentual_total": None,
        "divisor": None,
    }


def calcular(dados: dict, parametros: Optional[dict] = None) -> Dict[str, Any]:
    """Calcula o preço sugerido a partir dos custos já preenchidos na ficha.

    Devolve sempre um dict com a mesma forma -- `calculavel=False` + `motivo` no lugar de exceção
    ou de um número inventado, porque isto é exibido numa tela de revisão: "não dá para calcular
    porque os percentuais somam 100%" é informação útil; um `500` ou um preço negativo não são.

    Os valores intermediários (`custo_total`, `percentual_total`, `divisor`) voltam junto de
    propósito: a UI (Task 20) mostra a conta por extenso, para o número não chegar como um
    veredito de caixa-preta que a pessoa não tem como conferir.
    """
    parametros_normalizados, erro = _normalizar_parametros(parametros)
    if erro:
        return _nao_calculavel(erro, parametros_padrao())

    soma, informadas, ausentes = _somar_custos(dados)
    if not informadas:
        return _nao_calculavel(
            "Nenhum custo foi informado ainda -- preencha ao menos uma categoria de custo.",
            parametros_normalizados,
            informadas,
            ausentes,
        )

    percentual_total = sum(Decimal(str(v)) for v in parametros_normalizados.values())
    divisor = Decimal("1") - (percentual_total / Decimal("100"))

    if divisor <= 0:
        return _nao_calculavel(
            f"Imposto, comissão e margem somam {float(percentual_total):.2f}% -- para haver preço de venda, "
            "a soma precisa ser menor que 100%.",
            parametros_normalizados,
            informadas,
            ausentes,
        )

    return {
        "calculavel": True,
        "motivo": "",
        "preco_sugerido": _arredondar(soma / divisor),
        "custo_total": _arredondar(soma),
        "categorias_informadas": informadas,
        "categorias_ausentes": ausentes,
        "parametros": parametros_normalizados,
        "percentual_total": float(percentual_total),
        "divisor": float(divisor),
    }
