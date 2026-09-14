# -*- coding: utf-8 -*-
"""Renderização da ficha técnica no template .docx (Fase 11, Task 10).

Pega uma ficha persistida (`fichas_repo`) e produz o documento Word final, preenchendo o template
anotado na Task 9 (`templates/ficha_tecnica_v1.docx`) via docxtpl.

A divisão de responsabilidades aqui é deliberada e vale explicitar, porque é o que mantém o
documento fiel ao modelo original (a Prioridade 1 declarada pelo usuário):

- **O template manda no layout.** Nenhuma linha deste módulo cria parágrafo, tabela, borda ou
  fonte. O .docx original é aberto e preenchido -- nunca reconstruído.
- **Este módulo manda na apresentação do dado.** Número vira texto formatado em padrão brasileiro
  aqui, não no template (Jinja dentro de célula do Word é ilegível e impossível de testar) e não
  no frontend (o documento precisa sair correto mesmo gerado por uma rota chamada direto).
- **Valor ausente vira string vazia.** Nunca "None", nunca "0" -- a regra de não-invenção do
  produto vale também na impressão: campo sem informação sai em branco, como no formulário
  preenchido à mão.
"""

import os
from typing import Any, Dict, List, Optional

from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined

import fichas_logo
import fichas_modelo as fm
import fichas_repo
from fichas_template import (
    CAMINHO_TEMPLATE,
    MARCA_NAO_SELECIONADO,
    MARCA_SELECIONADO,
    TAMANHOS_GRADE,
)
from logger_config import obter_logger

NOME_ARQUIVO_DOCX = "ficha.docx"


# --- Formatação de valores ---------------------------------------------------------------------

def _texto(campo: Any) -> str:
    """Valor de texto pronto para impressão. Ausente/None vira string vazia."""
    valor = fm.valor_de(campo)
    return str(valor) if valor not in (None, "") else ""


def _formatar_dinheiro(valor: Optional[float]) -> str:
    """1234.5 -> "1.234,50". Sempre 2 casas: é dinheiro, "R$ 1.234,5" ficaria errado impresso."""
    if valor is None or valor == "":
        return ""
    try:
        # Formata no padrão en-US e troca os separadores -- evita depender de locale instalado no
        # sistema, que em servidor Linux enxuto normalmente não tem pt_BR.
        return f"{float(valor):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    except (TypeError, ValueError):
        return ""


def _formatar_quantidade(valor: Optional[float]) -> str:
    """Quantidades e medidas: 10 -> "10", 1.5 -> "1,5", 1.50 -> "1,5".

    Diferente de dinheiro, aqui forçar 2 casas atrapalharia a leitura -- "10,00 botões" e
    "1,50 m de largura" carregam uma precisão que o dado não tem.
    """
    if valor is None or valor == "":
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return ""
    if numero == int(numero):
        return str(int(numero))
    return f"{numero:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _dinheiro(campo: Any) -> str:
    return _formatar_dinheiro(fm.valor_de(campo))


def _quantidade(campo: Any) -> str:
    return _formatar_quantidade(fm.valor_de(campo))


# --- Montagem do contexto ----------------------------------------------------------------------

def _grade(dados: Dict[str, Any]) -> Dict[str, str]:
    """Mapa tamanho -> marca. Os dois tipos de grade (numérica e comercial) são unificados num
    dicionário só porque o template os desenha lado a lado, na mesma faixa de células."""
    grade = dados.get("grade") or {}
    selecionados = set(fm.valor_de(grade.get("numericos")) or [])
    selecionados.update(fm.valor_de(grade.get("comerciais")) or [])
    return {
        tamanho: (MARCA_SELECIONADO if tamanho in selecionados else MARCA_NAO_SELECIONADO)
        for tamanho in TAMANHOS_GRADE
    }


def _cores_beneficiamentos(dados: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {
            "item": _texto(linha.get("item")),
            "descricao": _texto(linha.get("descricao")),
            "cor": _texto(linha.get("cor")),
            "beneficiamento": _texto(linha.get("beneficiamento")),
            "observacoes": _texto(linha.get("observacoes")),
        }
        for linha in (dados.get("cores_beneficiamentos") or [])
    ]


def _aviamentos(dados: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {
            "descricao": _texto(linha.get("descricao")),
            "composicao": _texto(linha.get("composicao")),
            "cor": _texto(linha.get("cor")),
            "quantidade": _quantidade(linha.get("quantidade")),
            "fornecedor": _texto(linha.get("fornecedor")),
            "preco": _dinheiro(linha.get("preco")),
        }
        for linha in (dados.get("aviamentos") or [])
    ]


def _tecidos(dados: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {
            "descricao": _texto(linha.get("descricao")),
            "composicao": _texto(linha.get("composicao")),
            "cor": _texto(linha.get("cor")),
            "quantidade": _quantidade(linha.get("quantidade")),
            "largura": _quantidade(linha.get("largura")),
            "fornecedor": _texto(linha.get("fornecedor")),
            "preco": _dinheiro(linha.get("preco")),
        }
        for linha in (dados.get("tecidos") or [])
    ]


def _sequencia_operacional(dados: Dict[str, Any]) -> List[Dict[str, str]]:
    # A coluna ETAPA não vem daqui: o template numera pelo loop.index, então inserir/remover uma
    # operação na revisão nunca deixa a numeração impressa furada.
    return [
        {"descricao": _texto(linha.get("descricao")), "maquinas": _texto(linha.get("maquinas"))}
        for linha in (dados.get("sequencia_operacional") or [])
    ]


def _partes_modelagem(dados: Dict[str, Any]) -> List[Dict[str, str]]:
    """Partes da modelagem, com pelo menos uma linha sempre.

    No template, modelista e quantidade de moldes são impressos na primeira linha do laço das
    partes (`loop.first`). Se a lista chegasse vazia, o laço não rodaria nenhuma vez e a linha
    inteira sumiria -- levando junto dois dados que não têm nada a ver com as partes. Uma linha em
    branco garante que eles apareçam, e visualmente fica igual ao formulário original.
    """
    modelagem = dados.get("modelagem") or {}
    partes = [
        {"descricao": _texto(p.get("descricao")), "observacoes": _texto(p.get("observacoes"))}
        for p in (modelagem.get("partes") or [])
    ]
    return partes or [{"descricao": "", "observacoes": ""}]


def montar_contexto(ficha: Dict[str, Any]) -> Dict[str, Any]:
    """Traduz a ficha persistida no contexto que o template espera.

    Os nomes das chaves aqui são o contrato com o .docx -- `fichas_template.PLACEHOLDERS_ESCALARES`
    e `PLACEHOLDERS_LISTA` listam os mesmos nomes, e um teste compara os dois lados.
    """
    dados = ficha.get("dados") or fm.dados_vazios()
    identificacao = dados.get("ficha") or {}
    custos = dados.get("custos") or {}
    modelagem = dados.get("modelagem") or {}

    def custo(categoria: str) -> str:
        return _dinheiro((custos.get(categoria) or {}).get("custo"))

    def observacao(categoria: str) -> str:
        return _texto((custos.get(categoria) or {}).get("observacao"))

    return {
        # Imagens: preenchidas pelo logo (Task 11) e pelo desenho aprovado (Task 18). Vazias aqui
        # renderizam como espaço em branco, que é o estado correto de uma ficha sem elas.
        "logo": "",
        "desenho_tecnico": "",

        "ref": _texto(identificacao.get("ref")),
        "nome": _texto(identificacao.get("nome")),
        "colecao": _texto(identificacao.get("colecao")),
        "descricao": _texto(identificacao.get("descricao")),
        "designer": _texto(identificacao.get("designer")),
        "tecnica": _texto(identificacao.get("tecnica")),
        "empresa": _texto(identificacao.get("empresa")),
        "data": _texto(identificacao.get("data")),

        "cores_beneficiamentos": _cores_beneficiamentos(dados),
        "grade": _grade(dados),
        "aviamentos": _aviamentos(dados),
        "tecidos": _tecidos(dados),

        "custo_aviamentos": custo("aviamentos"),
        "custo_tecidos": custo("tecidos"),
        "custo_costura": custo("costura_beneficiamento"),
        "custo_outros": custo("outros"),
        "custo_total": custo("preco_total"),
        "obs_aviamentos": observacao("aviamentos"),
        "obs_tecidos": observacao("tecidos"),
        "obs_costura": observacao("costura_beneficiamento"),
        "obs_outros": observacao("outros"),
        "obs_total": observacao("preco_total"),

        "sequencia_operacional": _sequencia_operacional(dados),

        "modelista": _texto(modelagem.get("modelista")),
        "numero_moldes": _quantidade(modelagem.get("numero_moldes")),
        "partes": _partes_modelagem(dados),
    }


# --- Render ------------------------------------------------------------------------------------

def renderizar_para_arquivo(
    ficha: Dict[str, Any],
    caminho_saida: str,
    caminho_template: str = CAMINHO_TEMPLATE,
    tenant_id: Optional[str] = None,
) -> str:
    """Renderiza a ficha no template e salva em `caminho_saida`. Devolve o caminho salvo.

    Duas escolhas no ambiente Jinja que mudam bastante o comportamento em caso de erro:

    - `StrictUndefined`: uma variável que o template usa mas o contexto não fornece levanta
      exceção em vez de virar campo em branco. Sem isso, esquecer uma chave aqui produziria uma
      ficha impressa com o "PREÇO TOTAL" vazio, sem erro em lugar nenhum -- o tipo exato de falha
      silenciosa que este projeto trata como inaceitável.
    - `autoescape`: o conteúdo é injetado dentro do XML do .docx. Um fornecedor chamado
      "Pano & Cia" ou uma observação com "<" quebrariam o XML e o Word recusaria abrir o arquivo
      ("conteúdo ilegível"). Com autoescape, viram entidades XML válidas.
    """
    modelo = DocxTemplate(caminho_template)

    contexto = montar_contexto(ficha)
    if tenant_id:
        # O InlineImage precisa da instância do template (ele registra a imagem como relação
        # interna do .docx), então o logo só pode ser resolvido aqui, não em montar_contexto --
        # que é puro de propósito, para ser testável sem tocar em arquivo nenhum.
        contexto["logo"] = fichas_logo.logo_para_documento(modelo, tenant_id) or ""

    ambiente = Environment(undefined=StrictUndefined)
    modelo.render(contexto, ambiente, autoescape=True)

    diretorio = os.path.dirname(caminho_saida)
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    modelo.save(caminho_saida)
    return caminho_saida


def gerar_docx_da_ficha(
    tenant_id: str,
    ficha: Dict[str, Any],
    caminho_template: str = CAMINHO_TEMPLATE,
) -> str:
    """Gera o .docx dentro da pasta da própria ficha e devolve o caminho.

    Não atualiza o registro da ficha (status, `documentos.docx`) -- isso é decisão de quem chamou,
    normalmente a rota HTTP (Task 12), que é quem sabe se a geração foi um download avulso ou a
    conclusão do fluxo.
    """
    caminho = fichas_repo.caminho_arquivo_da_ficha(tenant_id, ficha["id"], NOME_ARQUIVO_DOCX)
    try:
        return renderizar_para_arquivo(ficha, caminho, caminho_template, tenant_id=tenant_id)
    except Exception as e:
        obter_logger(tenant_id).error(
            f"Falha ao renderizar o .docx da ficha {ficha.get('id')}: {e}", exc_info=True
        )
        raise
