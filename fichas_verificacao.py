# -*- coding: utf-8 -*-
"""Verificador de proveniência da ficha técnica (Fase 11, Task 4).

Este é o módulo que torna a regra de não-invenção uma garantia de código, não uma promessa de
prompt. `fichas_extracao.py` confia na saída do modelo; este módulo audita essa saída depois,
sem nunca confiar de volta no que o modelo *diz* sobre si mesmo.

Duas travas independentes, nessa ordem:

1. **Verificação de honestidade da origem.** Se um campo foi marcado FORNECIDO, o `trecho`
   citado precisa ser mesmo um pedaço literal do texto que o usuário escreveu (comparação
   determinística, normalizada -- sem acento, sem diferença de maiúscula/minúscula, espaços
   colapsados). Se não for, o modelo estava blefando: a origem é rebaixada para INFERIDO.

2. **Allowlist de campos não-invejáveis.** Depois da verificação acima, qualquer campo listado em
   `fichas_modelo.CAMPOS_NAO_INFERIVEIS` que não tenha sobrevivido como FORNECIDO é zerado pelo
   código -- preço, composição, fornecedor, número de moldes etc. nunca chegam à ficha como
   "inferido"; ou vieram do usuário, ou ficam vazios.

Este módulo nunca lança exceção e nunca modifica o dict recebido -- devolve sempre uma cópia
corrigida mais a lista de alertas do que foi rebaixado/zerado, para a tela de revisão (Task 8)
mostrar ao usuário exatamente o que a IA tentou afirmar sem embasamento.
"""

import copy
import re
import unicodedata
from typing import Any, Generator, List, Tuple

import fichas_modelo as fm

SEVERIDADE_ALERTA = "alerta"

# Origens que sobrevivem à allowlist de campos críticos. Só FORNECIDO hoje -- OBSERVADO (leitura
# de imagem/documento anexado) ainda não é produzido por nenhum caminho de extração (Bloco C,
# ainda não implementado); quando existir, avaliar se também deve passar aqui.
ORIGENS_QUE_PROTEGEM_CAMPO_CRITICO = (fm.ORIGEM_FORNECIDO,)


def _alerta(codigo: str, campo: str, mensagem: str) -> dict:
    return {"codigo": codigo, "severidade": SEVERIDADE_ALERTA, "campo": campo, "mensagem": mensagem}


def _normalizar(texto: Any) -> str:
    """Casefold + remove acentos + colapsa espaços -- a mesma normalização nos dois lados (texto
    do usuário e trecho citado) é o que torna a comparação tolerante a diferença de caixa/acento
    sem abrir mão de ser uma checagem determinística (não é um segundo modelo julgando)."""
    if not texto or not isinstance(texto, str):
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sem_acento.casefold()).strip()


def _e_campo_proveniencia(no: Any) -> bool:
    return isinstance(no, dict) and set(no.keys()) == {"valor", "origem", "trecho"}


def _percorrer_campos(no: Any, caminho: str) -> Generator[Tuple[str, dict], None, None]:
    """Percorre `dados` e produz (caminho, campo) para cada campo folha {valor, origem, trecho}.

    Usa a mesma convenção de caminho de fichas_modelo.CAMPOS_NAO_INFERIVEIS ("aviamentos[].preco"
    para item de lista), para que os dois módulos falem a mesma linguagem de endereço de campo.
    """
    if isinstance(no, dict):
        if _e_campo_proveniencia(no):
            yield caminho, no
        else:
            for chave, sub in no.items():
                yield from _percorrer_campos(sub, f"{caminho}.{chave}" if caminho else chave)
    elif isinstance(no, list):
        for item in no:
            yield from _percorrer_campos(item, f"{caminho}[]")


def _valor_vazio_como(valor: Any) -> Any:
    """Valor "zerado" do mesmo tipo do valor anterior -- lista vira lista vazia, número vira
    None, texto vira string vazia. Nenhum campo de CAMPOS_NAO_INFERIVEIS hoje é lista, mas a
    função cobre o caso por completude caso um campo assim seja adicionado."""
    if isinstance(valor, list):
        return []
    if isinstance(valor, bool):
        return False
    if isinstance(valor, (int, float)):
        return None
    return ""


def verificar_proveniencia(dados: dict, texto_origem: str) -> Tuple[dict, List[dict]]:
    """Audita e corrige a proveniência de cada campo de `dados` contra `texto_origem`.

    Devolve (dados_corrigidos, alertas). `dados` nunca é modificado -- o chamador recebe uma
    cópia nova, então pode comparar antes/depois se precisar (ex: para destacar na revisão
    exatamente o que mudou).
    """
    dados_corrigidos = copy.deepcopy(dados)
    alertas: List[dict] = []
    texto_normalizado = _normalizar(texto_origem)
    campos_criticos = set(fm.CAMPOS_NAO_INFERIVEIS)

    for caminho, campo in _percorrer_campos(dados_corrigidos, ""):
        origem = campo.get("origem")

        if origem == fm.ORIGEM_FORNECIDO:
            trecho_normalizado = _normalizar(campo.get("trecho"))
            if not trecho_normalizado or trecho_normalizado not in texto_normalizado:
                campo["origem"] = fm.ORIGEM_INFERIDO
                origem = fm.ORIGEM_INFERIDO
                alertas.append(_alerta(
                    "origem_rebaixada", caminho,
                    f"O campo '{caminho}' foi marcado como FORNECIDO, mas o trecho citado não "
                    "corresponde ao texto original -- rebaixado para INFERIDO.",
                ))

        if caminho in campos_criticos and origem not in ORIGENS_QUE_PROTEGEM_CAMPO_CRITICO:
            valor_anterior = campo.get("valor")
            if valor_anterior not in (None, "", []):
                alertas.append(_alerta(
                    "campo_critico_zerado", caminho,
                    f"O campo crítico '{caminho}' não foi confirmado como fornecido pelo "
                    f"usuário (origem: {origem}) e foi zerado -- este tipo de dado nunca pode "
                    "ser inferido pela IA.",
                ))
            campo["valor"] = _valor_vazio_como(valor_anterior)
            campo["origem"] = fm.ORIGEM_DESCONHECIDO
            campo["trecho"] = ""

    return dados_corrigidos, alertas
