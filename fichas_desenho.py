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
from datetime import datetime
from typing import Any, Dict, Optional

import fichas_modelo as fm
import fichas_repo
from geracao_imagem import SUFIXO_TECNICO
from logger_config import obter_logger
from moderacao import validar_prompt_imagem
from usage_tracker import incrementar_uso, verificar_limite

PREFIXO_ARQUIVO = "desenho_v"


class PromptReprovadoError(ValueError):
    """O prompt do desenho não passou na moderação (fora de escopo de moda, ou conteúdo
    impróprio). Carrega o motivo devolvido pela própria moderação, para repassar ao usuário."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


class LimiteDeImagensExcedidoError(RuntimeError):
    """A cota diária de geração de imagens do tenant (usage_tracker, tipo "imagens" -- a mesma
    cota compartilhada com o Gerador de Croqui do chat, já que ambos custam a mesma chamada de
    API) foi atingida."""


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


# --- Orquestração: moderação + cota + versionamento (Fase 11, Task 16) -------------------------
#
# gerar_nova_versao() é o único ponto deste módulo que de fato gasta crédito de API -- os dois
# helpers abaixo (montar_prompt_visual/acumular_instrucao) são puros, sem chamada nenhuma, então
# são seguros de testar/chamar livremente.

def montar_prompt_visual(dados: Dict[str, Any]) -> str:
    """Monta o prompt técnico a partir dos dados já verificados da ficha -- nunca do texto bruto
    do usuário sozinho ("a geração da imagem deve receber um prompt técnico construído a partir
    dos dados estruturados", regra do produto). Só entra na descrição o que já está preenchido:
    não inventa gola, bolso ou fechamento que a ficha não mencione.
    """
    identificacao = dados.get("ficha") or {}
    linhas = []

    nome = fm.valor_de(identificacao.get("nome"))
    if nome:
        linhas.append(f"TIPO DE PEÇA: {nome}")

    descricao = fm.valor_de(identificacao.get("descricao"))
    if descricao:
        linhas.append(f"DESCRIÇÃO: {descricao}")

    cores = [fm.valor_de(c.get("cor")) for c in (dados.get("cores_beneficiamentos") or [])]
    cores = [c for c in cores if c]
    if cores:
        linhas.append(f"CORES: {', '.join(cores)}")

    tecidos = [fm.valor_de(t.get("descricao")) for t in (dados.get("tecidos") or [])]
    tecidos = [t for t in tecidos if t]
    if tecidos:
        linhas.append(f"TECIDOS: {', '.join(tecidos)}")

    return "\n".join(linhas)


def acumular_instrucao(instrucoes_anteriores: str, instrucao_adicional: str) -> str:
    """Concatena um novo ajuste às instruções já acumuladas de versões anteriores.

    gpt-image-1 não expõe seed/determinismo (geracao_imagem.py) -- "regenerar com instrução"
    sempre produz uma peça nova, nunca uma correção pontual da anterior. Acumular o texto (em vez
    de descartar o pedido antigo a cada nova tentativa) é o que dá ao modelo o contexto completo
    de novo a cada chamada, para os ajustes já pedidos não se perderem.
    """
    if not instrucao_adicional:
        return instrucoes_anteriores
    if not instrucoes_anteriores:
        return instrucao_adicional
    return f"{instrucoes_anteriores}\n{instrucao_adicional}"


def gerar_nova_versao(
    client: Any,
    tenant_id: str,
    ficha: Dict[str, Any],
    limite_imagens_dia: int,
    instrucao_adicional: str = "",
) -> Dict[str, Any]:
    """Gera uma nova versão do desenho técnico e devolve a ficha com ela anexada.

    Não persiste a ficha em disco -- quem chama decide quando salvar (mesma convenção de
    fichas_docx.py/fichas_pdf.py: este módulo só monta o resultado, a rota HTTP orquestra o
    disco). O status inicial da versão já sai como AGUARDANDO_APROVACAO: neste fluxo síncrono
    (pedido → resposta), não existe um momento intermediário em que a imagem está "gerada" mas
    ainda não visível ao usuário para decidir -- os dois acontecem na mesma resposta HTTP.

    A ordem moderação → cota → geração é a mesma que POST /chat/croqui/confirmar já usa: nenhuma
    chamada cara acontece se uma verificação mais barata antes dela já reprovou.

    Levanta PromptReprovadoError ou LimiteDeImagensExcedidoError sem chamar a API de geração de
    imagem -- nenhum dos dois gasta o crédito da geração em si.
    """
    versoes = ficha["desenho"]["versoes"]
    numero_versao = len(versoes) + 1

    instrucoes_anteriores = versoes[-1]["instrucoes_acumuladas"] if versoes else ""
    instrucoes_acumuladas = acumular_instrucao(instrucoes_anteriores, instrucao_adicional)

    prompt_visual = montar_prompt_visual(ficha["dados"])
    if instrucoes_acumuladas:
        prompt_visual = f"{prompt_visual}\nAJUSTES SOLICITADOS PELO USUÁRIO:\n{instrucoes_acumuladas}"

    prompt_completo = f"{prompt_visual}{SUFIXO_TECNICO}"

    resultado_moderacao = validar_prompt_imagem(client, prompt_completo, tenant_id)
    if not resultado_moderacao.get("aprovado", False):
        raise PromptReprovadoError(
            resultado_moderacao.get("motivo", "O pedido contém elementos fora do escopo de moda e vestuário.")
        )

    if not verificar_limite(tenant_id, "imagens", limite_imagens_dia, quantidade_necessaria=1):
        raise LimiteDeImagensExcedidoError("Limite diário de geração de imagens atingido. Novas gerações estarão disponíveis amanhã.")

    conteudo = gerar_imagem_desenho(client, prompt_completo, tenant_id)
    if conteudo is None:
        raise RuntimeError("Falha ao gerar o desenho técnico. Tente novamente em instantes.")

    salvar_desenho(tenant_id, ficha["id"], numero_versao, conteudo)
    incrementar_uso(tenant_id, "imagens")

    ficha["desenho"]["solicitado"] = True
    ficha["desenho"]["versoes"] = versoes + [{
        "versao": numero_versao,
        "prompt_visual": prompt_visual,
        "instrucoes_acumuladas": instrucoes_acumuladas,
        "status": fm.DESENHO_AGUARDANDO_APROVACAO,
        "criado_em": datetime.now().isoformat(),
    }]
    return ficha


def aprovar_versao(ficha: Dict[str, Any], numero_versao: int) -> Dict[str, Any]:
    """Marca uma versão do desenho como aprovada -- só ela poderá entrar no documento final (Task
    18). Nenhum desenho é aprovado automaticamente; isso só acontece por ação explícita do
    usuário, nunca como efeito colateral de gerar ou visualizar.

    Rebaixa qualquer outra versão que estivesse marcada como aprovada de volta para
    "aguardando_aprovacao" -- só uma pode valer por vez, e `versao_aprovada` é um único número.
    """
    versoes = ficha["desenho"]["versoes"]
    if not any(v["versao"] == numero_versao for v in versoes):
        raise ValueError(f"Versão {numero_versao} não existe nesta ficha.")

    for v in versoes:
        if v["versao"] == numero_versao:
            v["status"] = fm.DESENHO_APROVADO
        elif v["status"] == fm.DESENHO_APROVADO:
            v["status"] = fm.DESENHO_AGUARDANDO_APROVACAO

    ficha["desenho"]["versao_aprovada"] = numero_versao
    return ficha
