# -*- coding: utf-8 -*-
"""Motor do agente sobre a Responses API da OpenAI (Fase 10, Bloco B).

Substitui, em paridade funcional, geracao_imagem.chamar_agente() (Chat Completions) -- criado
como módulo separado, ainda não plugado em nenhuma rota (ver api/main.py), para que a troca do
motor aconteça numa task própria (Fase 10, Task 4) depois de validada isoladamente.

POR QUE TROCAR DE API:
    web_search nativo (busca real na web da própria OpenAI, Fase 10, Bloco C) só existe na
    Responses API -- Chat Completions não o suporta (confirmado contra a documentação oficial e
    contra a API real antes de qualquer código ser escrito). Function calling (as ferramentas do
    registry em agente_ferramentas.py) também funciona na Responses API, num formato de schema
    "flat" diferente do formato aninhado que Chat Completions exige -- por isso
    agente_ferramentas.Ferramenta.para_schema() já gera no formato certo.

DIFERENÇAS DE FORMATO EM RELAÇÃO AO MOTOR ANTERIOR:
    - Chat Completions tem um "loop de mensagens" (role: system/user/assistant/tool) todo dentro
      de `messages`. Responses API separa o prompt de sistema em `instructions` (string) do
      histórico de turnos em `input` (lista de itens) -- por isso este módulo não recebe nem monta
      um prompt de sistema, só instructions + input.
    - Uma chamada de ferramenta some como `message.tool_calls` e vira um item de tipo
      "function_call" na lista `response.output`, com `call_id`/`name`/`arguments` soltos (não
      aninhados em `.function`).
    - web_search NÃO passa por este loop: o servidor da OpenAI executa a busca sozinho dentro da
      mesma chamada e devolve só o resultado final + um item "web_search_call" informativo. Só
      as ferramentas do nosso registry (function calling) geram uma parada real que precisamos
      executar e devolver.
    - Serialização: `item.model_dump()` puro inclui um campo `async_` que a API rejeita com 400
      ("Unknown parameter: 'input[x].async_'. Did you mean 'async'?") -- confirmado contra a API
      real. É preciso `model_dump(by_alias=True, exclude_none=True)`. Ver _serializar_item().

FLUXO DE CONFIRMAÇÃO (gerar_imagem_croqui/gerar_ficha_tecnica), preservado:
    Quando o modelo chama uma ferramenta marcada `exige_confirmacao=True` no registry, o loop
    para e devolve `pendente` em vez de executar -- o custo real (chamada de geração de imagem)
    só acontece depois que o usuário confirmar explicitamente (POST /chat/croqui/confirmar,
    inalterado na forma, adaptado ao formato Responses API na Task 4). `pendente["input_previo"]`
    e `pendente["function_call_item"]` carregam tudo que é preciso para retomar a mesma conversa
    exatamente de onde parou.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from agente_ferramentas import ContextoExecucao, executar_ferramenta, exige_confirmacao, resumir_para_log, schemas_para
from logger_config import obter_logger
from rag_config import OPENAI_TEXT_MODEL

# Rodadas de function-calling que exigimos executar localmente e re-chamar a API (web_search não
# conta aqui -- é resolvido pelo próprio servidor dentro de uma única chamada). Rede de segurança
# contra um modelo que insista em encadear ferramentas indefinidamente; native max_tool_calls
# (abaixo) já limita isso do lado da OpenAI, isto é uma segunda trava independente.
MAX_RODADAS_FERRAMENTA = 5

# Limite nativo da Responses API para chamadas de ferramenta dentro de uma única invocação de
# client.responses.create (cobre principalmente rodadas internas de web_search, que o servidor
# decide sozinho quantas vezes repetir).
MAX_TOOL_CALLS_NATIVO = 6

MAX_OUTPUT_TOKENS = 2048

TAMANHO_CONTEXTO_WEB_SEARCH = "low"


@dataclass
class RespostaAgente:
    """Resultado de uma chamada ao agente -- substitui a tupla posicional de 5 elementos do
    motor anterior por campos nomeados, mais fácil de estender sem quebrar quem já consome."""

    texto: Optional[str] = None
    imagem_url: Optional[str] = None
    pendente_confirmacao: Optional[Dict[str, Any]] = None
    fontes: List[Dict[str, str]] = field(default_factory=list)
    usou_web_search: bool = False


def montar_input_historico(mensagem: str, historico: Optional[List[Any]]) -> List[Dict[str, str]]:
    """Converte o histórico de chat (payload.historico da rota /chat) em itens de `input` da
    Responses API. Sem histórico, usa só a mensagem atual -- mesmo comportamento do motor anterior.
    """
    if not historico:
        return [{"role": "user", "content": mensagem}]

    itens = []
    for m in historico:
        role = getattr(m, "role", None)
        role = "assistant" if role in ("assistant", "IA") else (role or "user")
        itens.append({"role": role, "content": getattr(m, "content", "")})
    return itens


def _parse_argumentos(bruto: str) -> Dict[str, Any]:
    try:
        dados = json.loads(bruto)
        return dados if isinstance(dados, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _serializar_item(item: Any) -> Dict[str, Any]:
    """Serializa um item de response.output para reenviar em `input` na próxima chamada.

    model_dump() puro inclui um campo `async_` inválido para a API (ver docstring do módulo) --
    by_alias+exclude_none evita isso. Aceita também um dict puro (já serializado), útil em testes.
    """
    if isinstance(item, dict):
        return item
    return item.model_dump(by_alias=True, exclude_none=True)


def _extrair_citacoes_web_search(output_items: List[Any]) -> List[Dict[str, str]]:
    """Varre os itens de mensagem em busca de anotações url_citation (fontes do web_search)."""
    citacoes: List[Dict[str, str]] = []
    for item in output_items:
        if getattr(item, "type", None) != "message":
            continue
        for conteudo in getattr(item, "content", None) or []:
            if getattr(conteudo, "type", None) != "output_text":
                continue
            texto = getattr(conteudo, "text", "") or ""
            for anot in getattr(conteudo, "annotations", None) or []:
                if getattr(anot, "type", None) != "url_citation":
                    continue
                inicio, fim = getattr(anot, "start_index", 0), getattr(anot, "end_index", 0)
                trecho = texto[inicio:fim] if 0 <= inicio < fim <= len(texto) else ""
                citacoes.append({
                    "titulo": getattr(anot, "title", "") or "",
                    "url": getattr(anot, "url", "") or "",
                    "trecho": trecho,
                })
    return citacoes


def _extrair_tokens(resposta: Any) -> Tuple[int, int]:
    """Lê tokens de input/output de uma resposta da Responses API (resposta.usage.input_tokens/
    output_tokens), devolvendo (0, 0) se o objeto não tiver esse formato -- acontece em testes
    mockados sem `usage` configurado, e não deve quebrar o log por isso (observabilidade nunca
    pode ser a causa de uma falha na resposta real ao usuário)."""
    usage = getattr(resposta, "usage", None)
    try:
        entrada = int(getattr(usage, "input_tokens", 0) or 0)
        saida = int(getattr(usage, "output_tokens", 0) or 0)
        return entrada, saida
    except (TypeError, ValueError):
        return 0, 0


def _extrair_pergunta_resumida(input_items: List[Dict[str, Any]]) -> str:
    """Resumo curto da última mensagem do usuário, só para log -- NUNCA o conteúdo integral
    (ver a nota de privacidade em logger_config.py: prompt bruto do usuário não é logado)."""
    for item in reversed(input_items):
        if isinstance(item, dict) and item.get("role") == "user":
            return resumir_para_log(item.get("content", ""))
    return ""


def _logar_invocacao(
    logger: Any,
    pergunta_resumida: str,
    rodadas: int,
    tokens_entrada: int,
    tokens_saida: int,
    duracao_ms: int,
    usou_web_search: bool,
    pendente: bool = False,
    erro: bool = False,
) -> None:
    """Log estruturado de uma invocação completa do agente (Fase 10, Task 9) -- complementa o log
    por ferramenta já existente em agente_ferramentas.executar_ferramenta() com a visão de nível
    superior que faltava: qual foi a pergunta (resumida), quantas rodadas de tool-calling local
    ocorreram, quantos tokens a invocação consumiu ao todo (soma de todas as chamadas ao modelo
    dentro desta invocação, incluindo a rodada de fallback sem tools se houver), latência total, e
    se terminou em resposta final, pendente de confirmação, ou erro degradado.
    """
    logger.info(
        f"agente pergunta={pergunta_resumida} rodadas={rodadas} tokens_in={tokens_entrada} "
        f"tokens_out={tokens_saida} duracao_ms={duracao_ms} web_search={usou_web_search} "
        f"pendente_confirmacao={pendente} erro={erro}"
    )


def _normalizar_fontes_de_tool(dados_extras: Dict[str, Any]) -> List[Dict[str, str]]:
    """Uniformiza o campo "fontes" que ferramentas diferentes podem preencher em formatos
    diferentes: buscar_documentos_internos devolve uma lista de strings "documento.pdf (Página N)"
    (não há URL real para um documento interno); uma tool futura que cite fontes com URL real
    devolveria dicts {titulo,url,trecho} -- mesmo formato que buscar_tendencias_web (Tavily) usava
    antes de ser removida na Fase 10, Task 6 (substituída por web_search nativo). Mantido genérico
    para não precisar mudar de novo na próxima tool que citar fontes.
    """
    fontes_raw = dados_extras.get("fontes")
    if not fontes_raw:
        return []
    normalizadas = []
    for f in fontes_raw:
        if isinstance(f, dict):
            normalizadas.append({"titulo": f.get("titulo", ""), "url": f.get("url", ""), "trecho": f.get("trecho", "")})
        else:
            normalizadas.append({"titulo": str(f), "url": "", "trecho": ""})
    return normalizadas


def chamar_agente(
    client: Any,
    instructions: str,
    nomes_ferramentas: Optional[List[str]],
    input_inicial: List[Dict[str, Any]],
    contexto: ContextoExecucao,
    usar_web_search: bool = False,
) -> RespostaAgente:
    """Chama o agente (Responses API) até obter uma resposta final, executar ferramentas locais
    (function calling), ou parar pedindo confirmação do usuário para uma ferramenta cara.

    `nomes_ferramentas` são nomes registrados em agente_ferramentas -- o schema é resolvido aqui,
    nunca declarado pelo chamador (mesma centralização que fez as tools pararem de divergir entre
    schema e execução, ver agente_ferramentas.py). `usar_web_search` liga o web_search nativo lado
    a lado com essas ferramentas -- o próprio modelo decide qual (ou nenhuma) usar por turno.
    """
    logger = obter_logger(contexto.tenant_id)

    tools: List[Dict[str, Any]] = list(schemas_para(nomes_ferramentas))
    if usar_web_search:
        tools.append({"type": "web_search", "search_context_size": TAMANHO_CONTEXTO_WEB_SEARCH})

    imagem_url: Optional[str] = None
    fontes: List[Dict[str, str]] = []
    usou_web_search = False
    input_atual = list(input_inicial)
    rodada = 0
    tempo_inicio = time.monotonic()
    tokens_entrada_total = 0
    tokens_saida_total = 0
    pergunta_resumida = _extrair_pergunta_resumida(input_inicial)

    while True:
        try:
            resposta = client.responses.create(
                model=OPENAI_TEXT_MODEL,
                instructions=instructions,
                input=input_atual,
                tools=tools or None,
                tool_choice="auto" if tools else None,
                max_tool_calls=MAX_TOOL_CALLS_NATIVO if tools else None,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
        except Exception as api_err:
            if rodada == 0:
                # Rede de segurança equivalente à do motor anterior: se o modelo/conta não
                # suportar as tools configuradas, tenta uma vez sem elas em vez de propagar 500.
                err_str = str(api_err).lower()
                if tools and any(kw in err_str for kw in ["tool", "search", "not supported", "invalid"]):
                    logger.warning(f"Chamada com tools falhou, tentando fallback sem tools: {api_err}")
                    resposta_fallback = client.responses.create(
                        model=OPENAI_TEXT_MODEL,
                        instructions=instructions,
                        input=input_atual,
                        max_output_tokens=MAX_OUTPUT_TOKENS,
                    )
                    te, ts = _extrair_tokens(resposta_fallback)
                    _logar_invocacao(
                        logger, pergunta_resumida, rodada, te, ts,
                        int((time.monotonic() - tempo_inicio) * 1000), False,
                    )
                    return RespostaAgente(texto=resposta_fallback.output_text)
                # Falha na primeiríssima chamada, sem relação com tools -- nada foi tentado ainda,
                # nada a degradar. Logar antes de propagar: sem isso, o único rastro do erro seria
                # o 500 genérico que o FastAPI devolve, sem contexto nenhum de tenant/pergunta.
                logger.error(f"Falha na chamada inicial ao agente: {api_err}", exc_info=True)
                _logar_invocacao(
                    logger, pergunta_resumida, rodada, 0, 0,
                    int((time.monotonic() - tempo_inicio) * 1000), False, erro=True,
                )
                raise
            # Já executamos ao menos uma ferramenta local com sucesso -- degrada com o que já
            # temos em vez de perder o resultado obtido até aqui.
            logger.error(f"Falha ao continuar a conversa após executar ferramenta(s): {api_err}", exc_info=True)
            _logar_invocacao(
                logger, pergunta_resumida, rodada, tokens_entrada_total, tokens_saida_total,
                int((time.monotonic() - tempo_inicio) * 1000), usou_web_search, erro=True,
            )
            return RespostaAgente(
                texto="Não consegui concluir a resposta agora. Tente novamente em instantes.",
                imagem_url=imagem_url,
                fontes=fontes,
                usou_web_search=usou_web_search,
            )

        te, ts = _extrair_tokens(resposta)
        tokens_entrada_total += te
        tokens_saida_total += ts

        if any(getattr(item, "type", None) == "web_search_call" for item in resposta.output):
            usou_web_search = True
        fontes.extend(_extrair_citacoes_web_search(resposta.output))

        function_calls = [item for item in resposta.output if getattr(item, "type", None) == "function_call"]

        if not function_calls:
            _logar_invocacao(
                logger, pergunta_resumida, rodada, tokens_entrada_total, tokens_saida_total,
                int((time.monotonic() - tempo_inicio) * 1000), usou_web_search,
            )
            return RespostaAgente(
                texto=resposta.output_text,
                imagem_url=imagem_url,
                fontes=fontes,
                usou_web_search=usou_web_search,
            )

        # Ferramentas caras (gerar_imagem_croqui/gerar_ficha_tecnica) nunca executam por conta
        # própria -- têm prioridade sobre qualquer outra tool chamada na mesma rodada, mesmo
        # comportamento do motor anterior (FERRAMENTAS_COM_CONFIRMACAO).
        call_confirmacao = next((c for c in function_calls if exige_confirmacao(c.name)), None)
        if call_confirmacao is not None:
            argumentos = _parse_argumentos(call_confirmacao.arguments)
            pendente = {
                "tool_call_id": call_confirmacao.call_id,
                "nome_ferramenta": call_confirmacao.name,
                "argumentos": argumentos,
                "prompt_visual": argumentos.get("prompt_visual", ""),
                "resumo_confirmacao": argumentos.get("resumo_confirmacao", ""),
                "estilo_croqui": contexto.estilo_croqui,
                "input_previo": input_atual,
                "function_call_item": _serializar_item(call_confirmacao),
                # As instructions (prompt de sistema) usadas nesta chamada -- precisam ser as
                # MESMAS na retomada (retomar_apos_confirmacao), inclusive com qualquer contexto
                # de perfil_usuario já embutido nelas. Recalculá-las do zero no momento da
                # confirmação arriscaria divergir (ex: perda do perfil, que não trafega no
                # payload de /chat/croqui/confirmar).
                "instructions": instructions,
            }
            _logar_invocacao(
                logger, pergunta_resumida, rodada, tokens_entrada_total, tokens_saida_total,
                int((time.monotonic() - tempo_inicio) * 1000), usou_web_search, pendente=True,
            )
            return RespostaAgente(pendente_confirmacao=pendente, fontes=fontes, usou_web_search=usou_web_search)

        rodada += 1
        if rodada > MAX_RODADAS_FERRAMENTA:
            logger.warning(f"Loop de ferramentas excedeu {MAX_RODADAS_FERRAMENTA} rodadas -- encerrando com o texto disponível.")
            _logar_invocacao(
                logger, pergunta_resumida, rodada, tokens_entrada_total, tokens_saida_total,
                int((time.monotonic() - tempo_inicio) * 1000), usou_web_search, erro=True,
            )
            return RespostaAgente(
                texto=resposta.output_text or "Não consegui concluir a solicitação agora. Tente reformular o pedido.",
                imagem_url=imagem_url,
                fontes=fontes,
                usou_web_search=usou_web_search,
            )

        novos_itens = [_serializar_item(item) for item in resposta.output]
        for call in function_calls:
            argumentos = _parse_argumentos(call.arguments)
            resultado = executar_ferramenta(call.name, argumentos, contexto)
            if "imagem_url" in resultado.dados_extras:
                imagem_url = resultado.dados_extras["imagem_url"]
            fontes.extend(_normalizar_fontes_de_tool(resultado.dados_extras))
            novos_itens.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": resultado.conteudo,
            })

        input_atual = input_atual + novos_itens


def retomar_apos_confirmacao(
    client: Any,
    instructions: str,
    pendente: Dict[str, Any],
    resultado_ferramenta: str,
    tenant_id: Optional[str] = None,
) -> str:
    """Segundo passo do fluxo de confirmação: injeta o resultado da ferramenta (já executada
    pelo chamador, tipicamente após aprovação explícita do usuário) e obtém a resposta final.

    Não recebe `tools` -- depois de uma ferramenta com confirmação, a resposta final é só texto
    (descrição da peça/tabela de medidas), mesmo comportamento do motor anterior. `tenant_id` é
    opcional só para não quebrar chamadores/testes existentes que não o passam -- sem ele, o log
    desta chamada cai sob tenant "desconhecido" (ver logger_config.TenantAdapter).
    """
    tempo_inicio = time.monotonic()
    input_final = list(pendente["input_previo"]) + [
        pendente["function_call_item"],
        {
            "type": "function_call_output",
            "call_id": pendente["tool_call_id"],
            "output": resultado_ferramenta,
        },
    ]
    resposta = client.responses.create(
        model=OPENAI_TEXT_MODEL,
        instructions=instructions,
        input=input_final,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    tokens_entrada, tokens_saida = _extrair_tokens(resposta)
    obter_logger(tenant_id).info(
        f"agente_confirmacao ferramenta={pendente.get('nome_ferramenta', '')} "
        f"tokens_in={tokens_entrada} tokens_out={tokens_saida} "
        f"duracao_ms={int((time.monotonic() - tempo_inicio) * 1000)}"
    )
    return resposta.output_text
