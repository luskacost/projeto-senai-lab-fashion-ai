# -*- coding: utf-8 -*-
"""Registry declarativo das ferramentas (tools) disponíveis para o agente (Fase 10, Bloco A).

Antes disto, as ferramentas viviam espalhadas em dois lugares desconectados: o *schema* JSON
ficava embutido em tenant_config.py (por modo, no formato aninhado da API de Chat Completions) e
a *execução* ficava num if/elif em geracao_imagem.executar_ferramenta_local(). Nada garantia que
os dois lados concordassem -- dava pra declarar uma tool que ninguém sabia executar, ou executar
uma que ninguém declarou, e só se descobria em produção.

Aqui os dois lados viram uma coisa só: uma Ferramenta carrega o schema E o handler. O schema é
gerado a partir da própria declaração, no formato *flat* da Responses API
(`{"type": "function", "name": ..., "parameters": ...}`), diferente do formato aninhado
(`{"type": "function", "function": {...}}`) que a API de Chat Completions exige.

DECISÃO DE SEGURANÇA CENTRAL -- argumentos sensíveis nunca vêm do modelo:
    Nenhum schema de ferramenta declara `tenant_id`, `conversation_id` ou credenciais. Esses
    valores chegam ao handler pelo ContextoExecucao, montado pelo backend a partir da requisição
    HTTP autenticada. Ou seja, não existe *como* o modelo (ou um usuário instruindo o modelo, ou
    uma página web com prompt injection) escolher em qual tenant a ferramenta vai operar -- o
    isolamento multi-tenant não depende de o modelo se comportar bem. Ver Fase 10, Bloco D.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from logger_config import obter_logger

# Tamanho máximo do conteúdo que uma ferramenta pode devolver ao modelo. Resultados maiores são
# truncados: um retorno gigante (planilha inteira, dezenas de chunks de RAG) custa tokens de
# forma desproporcional e, pior, empurra o prompt de sistema pra longe do fim do contexto,
# enfraquecendo as regras de segurança. Ver o cenário "pesquisa que retorna muitos resultados"
# nos testes (Fase 10, Bloco G).
LIMITE_CONTEUDO_FERRAMENTA_CHARS = 8000

# Quanto de um valor aparece no log. O log registra *o que* a ferramenta recebeu e devolveu para
# permitir diagnóstico, mas nunca o conteúdo integral -- ver a nota de privacidade em
# logger_config.py.
LIMITE_RESUMO_LOG_CHARS = 200


@dataclass(frozen=True)
class ContextoExecucao:
    """Dados que o backend injeta na execução de uma ferramenta, fora do alcance do modelo.

    Tudo aqui vem da requisição HTTP validada (tenant existente, conversa do usuário), nunca dos
    argumentos gerados pelo LLM -- ver a nota de segurança no topo do módulo.
    """

    tenant_id: str
    conversation_id: Optional[str] = None
    perfil_usuario: Optional[str] = None
    estilo_croqui: Optional[str] = None
    # Client da OpenAI já autenticado, para ferramentas que precisam chamar a API (geração de
    # imagem). Fica no contexto em vez de ser criado dentro do handler para não espalhar leitura
    # de credencial por todo o código.
    client: Any = None


@dataclass
class ResultadoFerramenta:
    """Resultado da execução de uma ferramenta.

    Separa deliberadamente o que vai para o modelo (`conteudo`) do que vai para o usuário
    (`dados_extras`). Isso existe por um motivo concreto: a geração de imagem devolve uma data URI
    de vários megabytes em base64 -- mandá-la de volta ao modelo como conteúdo de mensagem
    queimaria o contexto inteiro e ainda convidaria o modelo a reproduzi-la no texto. O motor do
    agente repassa `conteudo` ao modelo e entrega `dados_extras` direto à camada HTTP.
    """

    conteudo: str
    erro: bool = False
    dados_extras: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Ferramenta:
    """Uma ferramenta disponível ao agente: schema + handler no mesmo lugar."""

    nome: str
    descricao: str
    propriedades: Dict[str, Any]
    obrigatorios: List[str]
    handler: Callable[[Dict[str, Any], ContextoExecucao], ResultadoFerramenta]
    # Ferramentas caras ou com efeito visível ao usuário param o loop do agente e pedem
    # confirmação explícita antes de executar (fluxo pendente_confirmacao, criado na Fase 7 para
    # gerar_imagem_croqui e reaproveitado aqui). É a proteção de "operação destrutiva/cara" da
    # Etapa 6: nenhuma dessas roda por decisão isolada do modelo.
    exige_confirmacao: bool = False

    def para_schema(self) -> Dict[str, Any]:
        """Schema no formato flat da Responses API."""
        return {
            "type": "function",
            "name": self.nome,
            "description": self.descricao,
            "parameters": {
                "type": "object",
                "properties": dict(self.propriedades),
                "required": list(self.obrigatorios),
                "additionalProperties": False,
            },
        }


class ErroValidacaoFerramenta(Exception):
    """Argumentos gerados pelo modelo não batem com o schema declarado."""


_REGISTRO: Dict[str, Ferramenta] = {}


def registrar(ferramenta: Ferramenta) -> Ferramenta:
    """Adiciona (ou substitui) uma ferramenta no registry global."""
    _REGISTRO[ferramenta.nome] = ferramenta
    return ferramenta


def obter_ferramenta(nome: str) -> Optional[Ferramenta]:
    return _REGISTRO.get(nome)


def listar_nomes() -> List[str]:
    return sorted(_REGISTRO.keys())


def exige_confirmacao(nome: str) -> bool:
    """True se a ferramenta só pode rodar após confirmação explícita do usuário."""
    ferramenta = _REGISTRO.get(nome)
    return bool(ferramenta and ferramenta.exige_confirmacao)


def schemas_para(nomes: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Schemas (formato Responses API) das ferramentas pedidas, ignorando nomes desconhecidos.

    Nome desconhecido é logado e descartado em vez de levantar exceção: uma configuração de modo
    com um nome errado degrada para "esse modo tem uma ferramenta a menos", não para "esse modo
    parou de responder".
    """
    if not nomes:
        return []

    schemas = []
    for nome in nomes:
        ferramenta = _REGISTRO.get(nome)
        if ferramenta is None:
            obter_logger().warning(f"Ferramenta '{nome}' referenciada na configuração não existe no registry -- ignorada.")
            continue
        schemas.append(ferramenta.para_schema())
    return schemas


_TIPOS_JSON = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def validar_argumentos(ferramenta: Ferramenta, argumentos: Dict[str, Any]) -> Dict[str, Any]:
    """Valida os argumentos contra o schema e devolve só os parâmetros declarados.

    Chaves não declaradas são descartadas (não repassadas ao handler): o modelo às vezes inventa
    um parâmetro extra, e repassá-lo às cegas a um handler é como confiar em entrada de usuário
    não validada. Levanta ErroValidacaoFerramenta se faltar obrigatório ou o tipo não bater.
    """
    if not isinstance(argumentos, dict):
        raise ErroValidacaoFerramenta("Os argumentos precisam ser um objeto JSON.")

    faltando = [p for p in ferramenta.obrigatorios if argumentos.get(p) in (None, "")]
    if faltando:
        raise ErroValidacaoFerramenta(f"Parâmetro(s) obrigatório(s) ausente(s): {', '.join(faltando)}.")

    limpos: Dict[str, Any] = {}
    for nome_param, spec in ferramenta.propriedades.items():
        if nome_param not in argumentos:
            continue
        valor = argumentos[nome_param]
        tipo_esperado = _TIPOS_JSON.get(spec.get("type", "string"))
        # bool é subclasse de int em Python: sem esta exceção, True passaria como "number".
        if tipo_esperado and not isinstance(valor, tipo_esperado):
            raise ErroValidacaoFerramenta(
                f"Parâmetro '{nome_param}' deveria ser do tipo {spec.get('type')}, veio {type(valor).__name__}."
            )
        if spec.get("type") in ("number", "integer") and isinstance(valor, bool):
            raise ErroValidacaoFerramenta(f"Parâmetro '{nome_param}' deveria ser numérico, veio booleano.")
        limpos[nome_param] = valor

    ignorados = set(argumentos) - set(ferramenta.propriedades)
    if ignorados:
        obter_logger().warning(
            f"Ferramenta '{ferramenta.nome}': parâmetro(s) não declarado(s) descartado(s): {', '.join(sorted(ignorados))}."
        )

    return limpos


def resumir_para_log(valor: Any, limite: int = LIMITE_RESUMO_LOG_CHARS) -> str:
    """Reduz um valor a uma linha curta segura para log (sem despejar conteúdo integral)."""
    try:
        texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)
    except Exception:
        texto = str(valor)
    texto = " ".join(texto.split())
    if len(texto) > limite:
        return f"{texto[:limite]}... [+{len(texto) - limite} chars]"
    return texto


def truncar_conteudo(conteudo: str, limite: int = LIMITE_CONTEUDO_FERRAMENTA_CHARS) -> str:
    """Corta um retorno grande demais, avisando o modelo de que houve corte.

    O aviso importa: sem ele o modelo trata o pedaço recebido como a resposta completa e pode
    afirmar com confiança que "não há mais registros".
    """
    if len(conteudo) <= limite:
        return conteudo
    return (
        conteudo[:limite]
        + f"\n\n[...resultado truncado em {limite} caracteres. Refine a consulta para obter menos resultados.]"
    )


def executar_ferramenta(nome: str, argumentos: Dict[str, Any], contexto: ContextoExecucao) -> ResultadoFerramenta:
    """Valida e executa uma ferramenta, sempre devolvendo um ResultadoFerramenta.

    Nunca propaga exceção: uma ferramenta que quebra precisa virar uma mensagem que o modelo
    consiga ler e contornar ("a busca falhou, responda com o que você sabe"), não um 500 que
    derruba a conversa inteira do usuário. Todo caminho de saída é logado com nome, argumentos
    resumidos, latência e sucesso/erro (Fase 10, Bloco E).
    """
    logger = obter_logger(contexto.tenant_id)
    ferramenta = _REGISTRO.get(nome)

    if ferramenta is None:
        logger.warning(f"Ferramenta desconhecida solicitada pelo modelo: '{nome}'")
        return ResultadoFerramenta(
            conteudo=f"[Erro] Ferramenta '{nome}' não existe. Nenhuma ação foi executada.",
            erro=True,
        )

    try:
        argumentos_limpos = validar_argumentos(ferramenta, argumentos)
    except ErroValidacaoFerramenta as err:
        logger.warning(f"Ferramenta '{nome}': argumentos inválidos -- {err}")
        return ResultadoFerramenta(conteudo=f"[Erro] Argumentos inválidos para '{nome}': {err}", erro=True)

    inicio = time.monotonic()
    try:
        resultado = ferramenta.handler(argumentos_limpos, contexto)
    except Exception as err:
        duracao_ms = int((time.monotonic() - inicio) * 1000)
        logger.error(
            f"tool={nome} status=excecao duracao_ms={duracao_ms} args={resumir_para_log(argumentos_limpos)} erro={err}",
            exc_info=True,
        )
        return ResultadoFerramenta(
            conteudo=f"[Erro] A ferramenta '{nome}' falhou ao executar. Prossiga sem esse dado ou avise o usuário.",
            erro=True,
        )

    duracao_ms = int((time.monotonic() - inicio) * 1000)
    resultado.conteudo = truncar_conteudo(resultado.conteudo)
    logger.info(
        f"tool={nome} status={'erro' if resultado.erro else 'ok'} duracao_ms={duracao_ms} "
        f"args={resumir_para_log(argumentos_limpos)} resultado={resumir_para_log(resultado.conteudo)}"
    )
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# FERRAMENTAS EXISTENTES, MIGRADAS PARA O REGISTRY
#
# As três ferramentas abaixo já existiam (Fases 7 e 8) declaradas em tenant_config.py no formato
# aninhado de Chat Completions e executadas por geracao_imagem.executar_ferramenta_local(). Aqui
# elas passam a ter uma declaração única. Os handlers delegam para as funções originais, que
# seguem sendo a implementação de verdade -- este bloco é a camada de declaração, não uma
# reescrita da lógica.
#
# Enquanto o motor novo (Bloco B) não entra no lugar de chamar_agente(), tenant_config.py mantém
# suas declarações antigas em paralelo; elas saem de lá na task que faz a troca do motor.
# ─────────────────────────────────────────────────────────────────────────────

DESCRICAO_PROMPT_VISUAL = "Descrição detalhada da peça em inglês: pose, silhueta, cores, tecido, fundo"


def _handler_gerar_imagem_croqui(argumentos: Dict[str, Any], contexto: ContextoExecucao) -> ResultadoFerramenta:
    """Gera o croqui de fato. Só é alcançado após confirmação explícita do usuário."""
    from geracao_imagem import (
        ESTILO_TECNICO,
        SUFIXO_TECNICO,
        chamar_api_geracao_imagem,
    )

    prompt_visual = argumentos.get("prompt_visual", "")
    if contexto.estilo_croqui == ESTILO_TECNICO:
        prompt_visual = f"{prompt_visual}{SUFIXO_TECNICO}"

    imagem = chamar_api_geracao_imagem(contexto.client, prompt_visual, contexto.tenant_id)
    if not imagem:
        return ResultadoFerramenta(
            conteudo="[Erro] Falha ao gerar a imagem. Tente novamente ou reformule a descrição.",
            erro=True,
        )
    # A data URI vai por dados_extras, NUNCA no conteúdo que volta pro modelo -- ver a docstring
    # de ResultadoFerramenta.
    return ResultadoFerramenta(
        conteudo="Imagem gerada com sucesso.",
        dados_extras={"imagem_url": imagem},
    )


def _handler_gerar_ficha_tecnica(argumentos: Dict[str, Any], contexto: ContextoExecucao) -> ResultadoFerramenta:
    """Desenho técnico da ficha. A tabela de medidas é redigida pelo modelo na resposta final --
    modelos de imagem não renderizam números legíveis, decisão validada na Fase 8."""
    from geracao_imagem import SUFIXO_TECNICO, chamar_api_geracao_imagem

    prompt_visual = f"{argumentos.get('prompt_visual', '')}{SUFIXO_TECNICO}"
    imagem = chamar_api_geracao_imagem(contexto.client, prompt_visual, contexto.tenant_id)

    sucesso_txt = "sucesso" if imagem else "falhou"
    conteudo = (
        f"Desenho técnico gerado ({sucesso_txt}, mostrando frente e costas na mesma imagem). "
        "Agora monte a tabela markdown estruturada de medidas/materiais/aviamentos conforme instruído."
    )
    return ResultadoFerramenta(
        conteudo=conteudo,
        erro=imagem is None,
        dados_extras={"imagem_url": imagem} if imagem else {},
    )


def _handler_buscar_tendencias_web(argumentos: Dict[str, Any], contexto: ContextoExecucao) -> ResultadoFerramenta:
    """Busca web via Tavily. Substituída pelo web_search nativo da OpenAI no Bloco C desta fase --
    mantida aqui para preservar o comportamento durante a migração do motor."""
    from geracao_imagem import buscar_tendencias_web

    texto, fontes = buscar_tendencias_web(argumentos.get("query", ""), contexto.tenant_id)
    return ResultadoFerramenta(
        conteudo=texto,
        erro=texto.startswith("[Erro]"),
        dados_extras={"fontes": fontes},
    )


registrar(Ferramenta(
    nome="gerar_imagem_croqui",
    descricao=(
        "Gera uma imagem de croqui de moda a partir de um prompt visual em inglês e um resumo "
        "simples em português para confirmação do usuário"
    ),
    propriedades={
        "prompt_visual": {
            "type": "string",
            "description": "Descrição detalhada do croqui em inglês: pose, silhueta, cores, tecido, fundo",
        },
        "resumo_confirmacao": {
            "type": "string",
            "description": (
                "Frase curta em português simples, sem jargões técnicos, descrevendo a peça para "
                "confirmação do usuário (ex: 'Um vestido midi floral, visto de frente')"
            ),
        },
    },
    obrigatorios=["prompt_visual", "resumo_confirmacao"],
    handler=_handler_gerar_imagem_croqui,
    exige_confirmacao=True,
))

registrar(Ferramenta(
    nome="gerar_ficha_tecnica",
    descricao=(
        "Gera uma ficha técnica de moda completa: desenho técnico (frente e costas) mais uma tabela "
        "estruturada de medidas, materiais e aviamentos, a partir da descrição de uma peça. Use em vez "
        "de gerar_imagem_croqui quando o usuário pedir explicitamente uma ficha técnica, medidas, "
        "materiais ou aviamentos -- não apenas um desenho."
    ),
    propriedades={
        "prompt_visual": {"type": "string", "description": DESCRICAO_PROMPT_VISUAL},
        "resumo_confirmacao": {
            "type": "string",
            "description": (
                "Frase curta em português simples confirmando que o usuário quer uma FICHA TÉCNICA "
                "completa (desenho + tabela de dados) da peça descrita, não só o desenho"
            ),
        },
    },
    obrigatorios=["prompt_visual", "resumo_confirmacao"],
    handler=_handler_gerar_ficha_tecnica,
    exige_confirmacao=True,
))

registrar(Ferramenta(
    nome="buscar_tendencias_web",
    descricao=(
        "Busca informações atuais na web (notícias, artigos, previsões de mercado) sobre tendências "
        "de moda, cores, coleções e comportamento de consumo."
    ),
    propriedades={
        "query": {
            "type": "string",
            "description": (
                "Termos de busca objetivos e específicos, em português ou inglês "
                "(ex: 'cores tendência primavera verão 2027 Pantone')"
            ),
        },
    },
    obrigatorios=["query"],
    handler=_handler_buscar_tendencias_web,
))
