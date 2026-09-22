# -*- coding: utf-8 -*-
"""Contrato e inspeção de placeholders do template .docx da ficha técnica (Fase 11, Task 9).

O template (`templates/ficha_tecnica_v1.docx`) é um arquivo binário que o usuário pode abrir e
editar no Word a qualquer momento. Isso cria um modo de falha silencioso e caro: ao editar uma
célula, o Word costuma **fatiar o texto em vários runs** (por revisão ortográfica, rsid, ou
simplesmente por onde o cursor passou), transformando `{{ ref }}` em `{{ re` + `f }}` no XML. O
Jinja do docxtpl só enxerga texto contíguo dentro de um run -- um placeholder fatiado deixa de ser
substituído e sai impresso *literalmente* no documento final, sem erro nenhum em lugar nenhum.

Este módulo existe para esse erro nunca passar despercebido:

- `PLACEHOLDERS_ESCALARES`/`PLACEHOLDERS_LISTA` são o contrato entre o template e o render
  (Task 10). Se o template perder um placeholder, o teste que compara contra estas tuplas falha.
- `inspecionar_template()` lê o .docx e devolve o que encontrou, incluindo placeholders quebrados
  por run splitting -- a checagem que nenhuma biblioteca faz por você.

Tudo aqui é read-only: nenhuma função deste módulo escreve no template.
"""

import os
import re
from typing import Any, Dict, List, Tuple

from docx import Document

CAMINHO_TEMPLATE = os.path.join("templates", "ficha_tecnica_v1.docx")

# Um placeholder completo: `{{ ... }}` (valor) ou `{% ... %}` (tag de controle do Jinja/docxtpl).
_REGEX_PLACEHOLDER = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)
# Abertura sem fechamento correspondente -- sinal de placeholder truncado/quebrado.
_REGEX_ABERTURA = re.compile(r"\{\{|\{%")
_REGEX_FECHAMENTO = re.compile(r"\}\}|%\}")
# Nome da variável dentro de `{{ ... }}`: pega "ref" em `{{ ref }}` e "a" em `{{ a.preco }}`.
_REGEX_NOME_VARIAVEL = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)")
# Nome da lista iterada em `{%tr for x in aviamentos %}`.
_REGEX_LISTA_ITERADA = re.compile(r"\{%\s*tr\s+for\s+\w+\s+in\s+([a-zA-Z_][a-zA-Z0-9_]*)")

# Valores únicos da ficha (um `{{ nome }}` cada). `ref` e `data` aparecem duas vezes no documento
# de propósito -- cabeçalho da página e bloco IDENTIFICAÇÃO DO PRODUTO mostram o mesmo dado.
PLACEHOLDERS_ESCALARES = (
    "logo",
    # Área do desenho técnico: não existia no formulário original (só no PDF de referência) e foi
    # acrescentada na Task 9, com aprovação do usuário -- sem ela o desenho aprovado no Bloco C
    # não teria onde ser impresso. Fica vazia enquanto não houver desenho aprovado.
    "desenho_tecnico",
    "ref",
    "nome",
    "colecao",
    "descricao",
    "designer",
    "tecnica",
    "empresa",
    "data",
    "custo_aviamentos",
    "custo_tecidos",
    "custo_costura",
    "custo_outros",
    "custo_total",
    "obs_aviamentos",
    "obs_tecidos",
    "obs_costura",
    "obs_outros",
    "obs_total",
    "modelista",
    "numero_moldes",
    # Fase 14, Bloco T, Task 27. Os três saem vazios quando não há preço calculável / a ficha não
    # está aprovada -- vazio é o estado correto, igual ao campo em branco do formulário impresso.
    "preco_sugerido",
    "aprovada_por",
    "aprovada_em",
)

# Tabelas que crescem conforme os dados, via `{%tr for ... %}` (a linha vira uma por item).
PLACEHOLDERS_LISTA = (
    "cores_beneficiamentos",
    "aviamentos",
    "tecidos",
    "sequencia_operacional",
    "partes",
    # Medidas por tamanho (Fase 14, Bloco M/T): a única tabela que cresce nas DUAS direções --
    # linhas por ponto de medida (`{%tr%}`) e colunas por tamanho da grade (`{%tc%}`).
    "medidas",
)

# A grade de tamanhos não é lista nem escalar: é um dicionário tamanho -> marca ("☑"/"□"), lido
# no template como `{{ grade['PP'] }}`. Chaves na mesma ordem em que aparecem impressas.
TAMANHOS_GRADE = (
    "PP", "P", "M", "G", "GG", "XG",
    "34", "36", "38", "40", "42", "44", "46", "48", "50", "52", "54", "56",
)

# Marcas usadas nas células da grade -- "□" é o mesmo caractere que já estava no template em
# branco, então uma ficha sem nenhum tamanho marcado sai visualmente idêntica ao formulário
# original impresso.
MARCA_SELECIONADO = "☑"
MARCA_NAO_SELECIONADO = "□"


def _paragrafos_do_documento(doc: Document) -> List[Tuple[str, Any]]:
    """Todos os parágrafos do documento, incluindo os de dentro de tabelas, com um rótulo de
    localização para as mensagens de erro serem acionáveis ("tabela 5, linha 1, coluna 2")."""
    paragrafos: List[Tuple[str, Any]] = []

    for indice, paragrafo in enumerate(doc.paragraphs):
        paragrafos.append((f"parágrafo {indice}", paragrafo))

    for indice_tabela, tabela in enumerate(doc.tables):
        for indice_linha, linha in enumerate(tabela.rows):
            for indice_coluna, celula in enumerate(linha.cells):
                for indice_paragrafo, paragrafo in enumerate(celula.paragraphs):
                    local = (
                        f"tabela {indice_tabela}, linha {indice_linha}, coluna {indice_coluna}"
                        f", parágrafo {indice_paragrafo}"
                    )
                    paragrafos.append((local, paragrafo))

    return paragrafos


def _detectar_quebrados(paragrafo: Any) -> List[str]:
    """Placeholders deste parágrafo que não cabem inteiros dentro de um único run.

    É exatamente o que o Word provoca ao reeditar uma célula, e o que faz o docxtpl deixar o
    placeholder passar sem substituir.
    """
    faixas_de_run: List[Tuple[int, int]] = []
    posicao = 0
    for run in paragrafo.runs:
        texto_run = run.text or ""
        faixas_de_run.append((posicao, posicao + len(texto_run)))
        posicao += len(texto_run)

    texto_completo = "".join(run.text or "" for run in paragrafo.runs)
    quebrados: List[str] = []

    for correspondencia in _REGEX_PLACEHOLDER.finditer(texto_completo):
        inicio, fim = correspondencia.span()
        cabe_em_um_run = any(ini <= inicio and fim <= f for ini, f in faixas_de_run)
        if not cabe_em_um_run:
            quebrados.append(correspondencia.group(0))

    # Abertura sem fechamento: o placeholder não só está fatiado, está truncado.
    if len(_REGEX_ABERTURA.findall(texto_completo)) != len(_REGEX_FECHAMENTO.findall(texto_completo)):
        quebrados.append(f"(abertura sem fechamento) {texto_completo[:60]!r}")

    return quebrados


def inspecionar_template(caminho: str = CAMINHO_TEMPLATE) -> Dict[str, Any]:
    """Lê o template e relata o que encontrou. Nunca escreve no arquivo.

    Retorna:
        {
          "placeholders": [str],      # todos os `{{...}}`/`{%...%}` achados, em ordem
          "variaveis": {str},         # nomes de variável usados em `{{ ... }}`
          "listas": {str},            # listas iteradas por `{%tr for ... %}`
          "quebrados": [(local, str)] # placeholders fatiados entre runs (o erro silencioso)
          "tabelas": [(linhas, colunas)],
        }
    """
    doc = Document(caminho)

    placeholders: List[str] = []
    variaveis = set()
    listas = set()
    quebrados: List[Tuple[str, str]] = []

    for local, paragrafo in _paragrafos_do_documento(doc):
        texto = "".join(run.text or "" for run in paragrafo.runs)
        if "{{" not in texto and "{%" not in texto:
            continue

        for correspondencia in _REGEX_PLACEHOLDER.finditer(texto):
            placeholders.append(correspondencia.group(0))

        variaveis.update(_REGEX_NOME_VARIAVEL.findall(texto))
        listas.update(_REGEX_LISTA_ITERADA.findall(texto))

        for quebrado in _detectar_quebrados(paragrafo):
            quebrados.append((local, quebrado))

    return {
        "placeholders": placeholders,
        "variaveis": variaveis,
        "listas": listas,
        "quebrados": quebrados,
        "tabelas": [(len(t.rows), len(t.columns)) for t in doc.tables],
    }


def formatar_relatorio(inspecao: Dict[str, Any]) -> str:
    """Relatório legível do resultado -- usado pelo script de preflight na linha de comando."""
    linhas = [
        f"Placeholders encontrados: {len(inspecao['placeholders'])}",
        f"Variáveis: {', '.join(sorted(inspecao['variaveis'])) or '(nenhuma)'}",
        f"Listas dinâmicas: {', '.join(sorted(inspecao['listas'])) or '(nenhuma)'}",
        f"Tabelas: {len(inspecao['tabelas'])} -> {inspecao['tabelas']}",
        "",
    ]

    if inspecao["quebrados"]:
        linhas.append(f"PLACEHOLDERS QUEBRADOS ({len(inspecao['quebrados'])}):")
        for local, quebrado in inspecao["quebrados"]:
            linhas.append(f"  - {local}: {quebrado}")
    else:
        linhas.append("Nenhum placeholder quebrado por run splitting.")

    return "\n".join(linhas)


if __name__ == "__main__":
    print(formatar_relatorio(inspecionar_template()))
