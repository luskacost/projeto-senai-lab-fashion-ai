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
from typing import Any, List, Optional

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


def _valor_numerico(campo: Any) -> Optional[float]:
    valor = fm.valor_de(campo)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def validar_medidas(dados: dict) -> List[dict]:
    """Alerta sobre a tabela de medidas por tamanho (Fase 14, Bloco M, Task 21).

    Medida nunca vem da extração (fm.CHAVES_NAO_EXTRAIDAS) -- tudo aqui foi digitado a mão, então
    os erros que importam são de digitação e de dessincronia com a grade, não de invenção da IA:

    - coluna que não corresponde a nenhum tamanho da grade (sobra de quando a grade foi alterada);
    - valor ≤ 0 (não existe medida negativa nem de zero centímetro);
    - progressão não monotônica entre tamanhos vizinhos -- o clássico "42" digitado onde era "24";
    - grade maior que as colunas que o documento comporta (fm.MAX_COLUNAS_MEDIDAS).

    Célula em branco NÃO gera alerta por célula (uma tabela pela metade num rascunho viraria uma
    enxurrada que esconde os alertas que importam): gera um alerta por linha, listando os tamanhos
    que faltam naquele ponto de medida.

    A progressão é checada dentro de cada família (numéricos entre si, comerciais entre si): a
    fronteira entre "56" e "PP" numa grade mista não é uma progressão real, e compará-los
    acusaria erro onde não há.
    """
    medidas = dados.get("medidas") if isinstance(dados, dict) else None
    if not isinstance(medidas, list) or not medidas:
        return []

    tamanhos = fm.tamanhos_da_grade(dados)
    alertas = []

    if len(tamanhos) > fm.MAX_COLUNAS_MEDIDAS:
        excedentes = tamanhos[fm.MAX_COLUNAS_MEDIDAS:]
        alertas.append(_alerta(
            "grade_excede_colunas_do_documento", "medidas",
            f"A grade tem {len(tamanhos)} tamanhos, mas a tabela de medidas do documento comporta "
            f"{fm.MAX_COLUNAS_MEDIDAS} colunas -- {', '.join(excedentes)} ficam de fora do arquivo "
            "gerado (continuam salvos na ficha).",
        ))

    for i, linha in enumerate(medidas):
        if not isinstance(linha, dict):
            continue
        caminho = f"medidas[{i}]"
        ponto = fm.valor_de(linha.get("ponto")) or ""
        rotulo = ponto or f"linha {i + 1}"
        valores = linha.get("valores")
        valores = valores if isinstance(valores, dict) else {}

        preenchidos = {t: v for t, v in ((t, _valor_numerico(c)) for t, c in valores.items()) if v is not None}

        if not ponto and preenchidos:
            alertas.append(_alerta(
                "medida_sem_ponto", f"{caminho}.ponto",
                f"A {rotulo} da tabela de medidas tem valores, mas não diz qual ponto de medida "
                "eles descrevem.",
            ))

        fora_da_grade = [t for t in valores if t not in tamanhos]
        if fora_da_grade:
            alertas.append(_alerta(
                "medida_fora_da_grade", caminho,
                f"Em '{rotulo}' há medida para {', '.join(sorted(fora_da_grade))}, que não "
                "está(ão) na grade de tamanhos desta ficha.",
            ))

        nao_positivos = sorted(t for t, v in preenchidos.items() if v <= 0)
        if nao_positivos:
            alertas.append(_alerta(
                "medida_nao_positiva", caminho,
                f"Em '{rotulo}', a medida de {', '.join(nao_positivos)} é zero ou negativa.",
            ))

        faltando = [t for t in tamanhos if t not in preenchidos]
        if preenchidos and faltando:
            alertas.append(_alerta(
                "medida_incompleta", caminho,
                f"'{rotulo}' não tem medida para: {', '.join(faltando)}.",
            ))

        for familia in (fm.TAMANHOS_NUMERICOS, fm.TAMANHOS_COMERCIAIS):
            da_familia = [t for t in tamanhos if t in familia and t in preenchidos]
            for anterior, seguinte in zip(da_familia, da_familia[1:]):
                if preenchidos[seguinte] < preenchidos[anterior]:
                    alertas.append(_alerta(
                        "medida_nao_progressiva", caminho,
                        f"Em '{rotulo}', o tamanho {seguinte} ({preenchidos[seguinte]:g}) mede menos "
                        f"que o {anterior} ({preenchidos[anterior]:g}) -- confira se não houve erro "
                        "de digitação.",
                    ))

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
    alertas.extend(validar_medidas(dados))
    return alertas
