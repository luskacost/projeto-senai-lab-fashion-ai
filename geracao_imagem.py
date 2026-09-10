# -*- coding: utf-8 -*-
"""Geração de imagens de croqui (DALL-E 3, OpenAI) e orquestração de tool calling.

Extraído de app.py para ser reaproveitado pela API sem depender do Streamlit. As duas únicas
dependências de st.session_state existentes na versão original (estilo_croqui) viraram
parâmetros explícitos.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

import requests

from logger_config import obter_logger
from rag_config import OPENAI_TEXT_MODEL
from tenant_config import obter_secret_tenant

SUFIXO_TECNICO = (
    ", fashion technical flat sketch, vector line art style, black and white line drawing, "
    "no human body, no color rendering, garment schematic, white background, technical fashion illustration"
)

ESTILO_ILUSTRACAO = "🎨 Ilustração de Moda"
ESTILO_TECNICO = "📐 Desenho Técnico (Flat Sketch)"

# Ferramentas que exigem confirmação prévia do usuário antes de gastar uma geração de imagem de
# verdade (ver o fluxo pendente_confirmacao em chamar_agente() abaixo e /chat/croqui/confirmar em
# api/main.py). gerar_ficha_tecnica (Fase 8) reusa o mesmo fluxo de gerar_imagem_croqui.
FERRAMENTAS_COM_CONFIRMACAO = {"gerar_imagem_croqui", "gerar_ficha_tecnica"}


# IMPORTANTE: validar_prompt_imagem() (moderacao.py) deve sempre rodar antes desta função,
# independente do provedor de imagem usado.
def chamar_api_geracao_imagem(client: Any, prompt_visual: str, tenant_id: str, tamanho: str = "1024x1792") -> Optional[str]:
    """Gera uma imagem via DALL-E 3 (OpenAI) a partir do prompt e retorna a URL temporária da
    imagem gerada (hospedada pela OpenAI, válida por cerca de 1h) -- ou None se a geração falhar
    (ex: rejeitada pelo filtro de conteúdo da própria OpenAI, erro de rede/quota).

    Substituiu o Pollinations.ai (Fase 9/Bloco A): diferente daquele provedor, a geração de fato
    acontece nesta chamada (síncrona) -- não é mais adiada para o navegador carregar a URL depois.
    `tamanho` default é retrato (1024x1792), mais próximo do enquadramento de figurino de moda
    que o antigo 512x768. Não há parâmetro de seed: nenhuma versão do DALL-E expõe controle de
    determinismo na API pública -- para consistência entre frente/costas do Desenho Técnico,
    contamos só com prompts bem descritivos (ver chamadas em api/main.py), sem garantia visual.
    """
    try:
        resposta = client.images.generate(
            model="dall-e-3",
            prompt=prompt_visual,
            size=tamanho,
            quality="standard",
            n=1,
        )
        return resposta.data[0].url
    except Exception as e:
        obter_logger(tenant_id).error(f"Falha ao gerar imagem via DALL-E 3: {e}", exc_info=True)
        return None


def buscar_tendencias_web(query: str, tenant_id: str) -> Tuple[str, List[Dict[str, str]]]:
    """Busca resultados atuais na web via Tavily.

    Substitui o antigo `{"type": "web_search"}` (não era uma tool válida para o modelo Groq
    configurado -- ver TODO/relatório da Fase 7, o modo "Tendências" alucinava respostas sem
    busca real nenhuma).

    Retorna (texto_formatado, fontes) -- texto_formatado é o bloco enviado de volta ao modelo
    como resultado da tool call; fontes é a lista estruturada [{"titulo", "url", "trecho"}] usada
    por _chat_via_agente (api/main.py) para popular fontes_consultadas/trechos_consultados na
    resposta da API, no mesmo padrão de citação já usado pelo modo "Base de Conhecimento".
    """
    api_key = obter_secret_tenant(tenant_id, "TAVILY_API_KEY")
    if not api_key:
        return f"[Erro] Busca na web indisponível: TAVILY_API_KEY não configurada para o tenant '{tenant_id}'.", []

    try:
        resposta = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": False,
            },
            timeout=15,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except Exception as e:
        return f"[Erro] Falha ao buscar na web: {e}", []

    resultados = dados.get("results", [])
    if not resultados:
        return "Nenhum resultado encontrado na busca web para essa consulta.", []

    blocos = []
    fontes: List[Dict[str, str]] = []
    for r in resultados:
        titulo = str(r.get("title", "")).strip()
        url = str(r.get("url", "")).strip()
        trecho = str(r.get("content", "") or "").strip()
        if len(trecho) > 500:
            trecho = trecho[:500] + "..."
        blocos.append(f"- {titulo}\n  URL: {url}\n  Trecho: {trecho}")
        fontes.append({"titulo": titulo, "url": url, "trecho": trecho})

    texto = "Resultados da busca web (cite a URL de cada fonte usada na resposta):\n\n" + "\n\n".join(blocos)
    return texto, fontes


def executar_ferramenta_local(
    client: Any,
    nome_ferramenta: str,
    argumentos: Dict[str, Any],
    tenant_id: str,
    estilo_croqui: str = ESTILO_ILUSTRACAO
) -> str:
    """Chama a função local correspondente ao nome_ferramenta e retorna o resultado.

    Para 'buscar_tendencias_web', usar chamar_agente() diretamente quando as fontes estruturadas
    forem necessárias -- este dispatcher genérico devolve só o texto formatado.
    """
    if nome_ferramenta == "gerar_imagem_croqui":
        prompt_visual = argumentos.get("prompt_visual", "")
        if estilo_croqui == ESTILO_TECNICO:
            prompt_visual = f"{prompt_visual}{SUFIXO_TECNICO}, front view"
        url = chamar_api_geracao_imagem(client, prompt_visual, tenant_id)
        return url if url else "[Erro] Falha ao gerar a imagem. Tente novamente ou reformule a descrição."
    if nome_ferramenta == "buscar_tendencias_web":
        texto, _fontes = buscar_tendencias_web(argumentos.get("query", ""), tenant_id)
        return texto
    return f"[Erro] Ferramenta '{nome_ferramenta}' não reconhecida. Nenhuma ação foi executada."


def chamar_agente(
    client: Any,
    agente_config: Dict[str, Any],
    messages_for_api: List[Dict[str, Any]],
    tenant_id: str,
    estilo_croqui: str = ESTILO_ILUSTRACAO
) -> Tuple[Optional[str], Optional[str], bool, Optional[Dict[str, Any]], List[Dict[str, str]]]:
    """Chama a API da Groq com suporte a tool calling quando o agente tiver tools.

    Se a ferramenta 'gerar_imagem_croqui' for detectada, retorna um sinal de confirmação
    pendente (pendente_dados) contendo os argumentos e o ID da chamada para aprovação prévia
    do usuário -- a geração da imagem em si só ocorre após confirmação explícita (ver
    api/main.py: POST /chat/croqui/confirmar).

    Retorna (texto_resposta, imagem_url, usou_fallback_sem_tools, pendente_dados, fontes_busca_web).
    """
    tools = agente_config.get("tools")
    imagem_url = None

    try:
        if tools is not None:
            primeira_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model=OPENAI_TEXT_MODEL,
                temperature=0.7,
                max_tokens=2048,
                tools=tools,
                tool_choice="auto",
            )
        else:
            primeira_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model=OPENAI_TEXT_MODEL,
                temperature=0.7,
                max_tokens=2048,
            )
    except Exception as api_err:
        err_str = str(api_err).lower()
        if tools is not None and any(kw in err_str for kw in ["tool", "search", "not supported", "invalid"]):
            primeira_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model=OPENAI_TEXT_MODEL,
                temperature=0.7,
                max_tokens=2048,
            )
            return primeira_resposta.choices[0].message.content, None, True, None, []
        raise

    message = primeira_resposta.choices[0].message
    fontes_busca_web: List[Dict[str, str]] = []

    # Loop limitado de rodadas de tool calling: uma ferramenta como buscar_tendencias_web pode
    # legitimamente ser chamada mais de uma vez (o modelo refina a busca), diferente de
    # gerar_imagem_croqui (sempre encerra a rodada, ver abaixo). Repassar "tools" em toda chamada
    # de acompanhamento evita um 400 da Groq ("Tool choice is none, but model called a tool") caso
    # o modelo decida chamar a ferramenta de novo -- encontrado em teste manual real.
    MAX_RODADAS_TOOL_CALLING = 3
    rodada = 0
    while hasattr(message, "tool_calls") and message.tool_calls and rodada < MAX_RODADAS_TOOL_CALLING:
        rodada += 1
        # gerar_ficha_tecnica (Fase 8) segue exatamente o mesmo fluxo de confirmação prévia que
        # gerar_imagem_croqui -- só muda o que acontece depois da confirmação (ver
        # /chat/croqui/confirmar em api/main.py).
        tc_com_confirmacao = next(
            (tc for tc in message.tool_calls if tc.function.name in FERRAMENTAS_COM_CONFIRMACAO), None
        )

        if tc_com_confirmacao is not None:
            croqui_tc = tc_com_confirmacao
            try:
                argumentos = json.loads(croqui_tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                argumentos = {}

            prompt_visual = argumentos.get("prompt_visual", "")
            resumo_confirmacao = argumentos.get("resumo_confirmacao", "")

            assistant_msg = {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }

            pendente_dados = {
                "tool_call_id": croqui_tc.id,
                "nome_ferramenta": croqui_tc.function.name,
                "argumentos": argumentos,
                "prompt_visual": prompt_visual,
                "resumo_confirmacao": resumo_confirmacao,
                "assistant_message": assistant_msg,
                "messages_for_api": list(messages_for_api),
                "estilo_croqui": estilo_croqui,
            }
            return None, None, False, pendente_dados, []

        # Para outras ferramentas (ex: buscar_tendencias_web), executa normalmente
        messages_for_api.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ],
        })

        for tool_call in message.tool_calls:
            try:
                argumentos = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                argumentos = {}

            if tool_call.function.name == "buscar_tendencias_web":
                resultado, fontes_tool = buscar_tendencias_web(argumentos.get("query", ""), tenant_id)
                fontes_busca_web.extend(fontes_tool)
            else:
                resultado = executar_ferramenta_local(client, tool_call.function.name, argumentos, tenant_id, estilo_croqui)

            if isinstance(resultado, str) and resultado.startswith("http"):
                imagem_url = resultado

            messages_for_api.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(resultado),
            })

        try:
            proxima_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model=OPENAI_TEXT_MODEL,
                temperature=0.7,
                max_tokens=2048,
                tools=tools,
                tool_choice="auto" if rodada < MAX_RODADAS_TOOL_CALLING else "none",
            )
        except Exception:
            # Rede de segurança: se mesmo com tool_choice="none" o modelo insistir em chamar uma
            # ferramenta (raro), a Groq rejeita a chamada -- encerra o loop com o que já foi
            # sintetizado/buscado em vez de propagar um 500 pro usuário.
            texto_parcial = message.content or "Não consegui concluir a busca agora. Tente novamente em instantes."
            return texto_parcial, imagem_url, False, None, fontes_busca_web
        message = proxima_resposta.choices[0].message

    return message.content, imagem_url, False, None, fontes_busca_web
