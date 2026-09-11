# Contrato da API

Referência dos endpoints REST expostos por `api/main.py` (FastAPI), consumidos pelo frontend
Next.js via `frontend/src/lib/api.ts`. Documenta o contrato **atual** — não um plano; para a
arquitetura de IA por trás de `/chat`, ver a seção "Arquitetura do agente" no `README.md`.

Convenção: `tenant_id` é sempre obrigatório. Multi-tenant na estrutura, uso single-tenant
(`senai_labfashion`) na prática hoje.

## Autenticação/Admin

### `POST /admin/login`
- **Body:** `{ tenant_id, senha }`
- **Lógica:** compara `senha` com `obter_secret_tenant(tenant_id, "ADMIN_PASSWORD")` via
  `hmac.compare_digest` (constant-time); bloqueio de 15min após 5 tentativas incorretas por tenant.
- **Resposta:** `{ autorizado: bool, token: string | null }` — `token` é opaco, válido por 4h,
  exigido no header `X-Admin-Token` nas rotas administrativas abaixo.

## Configuração do Tenant

### `GET /config/tenant?tenant_id=`
- **Resposta:** config mesclada (branding, prompts, modos, limites diários, cores) — não exige auth.

### `PUT /config/tenant`
- **Headers:** `X-Admin-Token`
- **Body:** `{ tenant_id, dados_custom }`

## Chat

### `POST /chat`
- **Body:** `{ tenant_id, conversation_id?, modo, perfil_usuario?, mensagem, historico?, estilo_croqui? }`
  — `historico` é a lista `{role, content}[]` da conversa (só enviada por modos baseados em
  agente, ver `frontend/src/lib/modos.ts:ehModoDeAgente`).
- **Checagem prévia:** `limite_mensagens_dia` do tenant (`config.get("limite_mensagens_dia", 200)`)
  — `429` se excedido, **antes** de qualquer chamada à OpenAI (sem custo).
- **Lógica por `modo`:**
  - **"Base de Conhecimento":** RAG puro — `buscar_contexto_relevante` → `montar_prompt_final` →
    `chat.completions.create` (Chat Completions, não passa pelo agente).
  - **"Análise de Dados":** `responder_pergunta_sobre_dados` sobre o resumo estatístico persistido
    por `conversation_id` (populado por `POST /planilha/upload`) — nunca vê os dados brutos.
  - **Todos os demais modos** (Consultor de Estilo, Professor Técnico, Engenharia Têxtil, Gerador
    de Croqui, Tendências, Assistente Geral): via o agente (`agente_openai.chamar_agente`,
    Responses API). Cada modo declara em `tenant_config.py` uma lista de nomes de ferramentas
    (resolvidas contra o registry em `agente_ferramentas.py`) e uma flag `usar_web_search`. O
    modelo decide sozinho se/quando chamar cada uma.
- **Resposta:**
  ```jsonc
  {
    "resposta": "string | null",       // null quando pendente_confirmacao não é null
    "imagem_url": "string | null",     // data URI base64 (data:image/png;base64,...) ou null
    "pendente_confirmacao": { ... } | null,  // ver abaixo -- opaco pro frontend
    "fontes_consultadas": ["string", ...],   // títulos das fontes citadas
    "trechos_consultados": [
      { "fonte": "string", "texto": "string", "url": "string | null" }
      // "url" só presente quando a fonte veio de busca real na web (web_search nativo);
      // ausente/null para documentos internos (RAG) ou dados do sistema
    ],
    "usou_busca_web": true | false     // distingue "respondeu de conhecimento próprio" de
                                        // "pesquisou antes de responder" -- só relevante nos
                                        // modos com usar_web_search habilitado
  }
  ```
- **`pendente_confirmacao`** (não `null`): o modelo decidiu chamar uma ferramenta que exige
  aprovação prévia (hoje, `gerar_imagem_croqui`/`gerar_ficha_tecnica` — as únicas marcadas
  `exige_confirmacao=True` no registry). O frontend guarda esse objeto em memória (opaco, nunca
  inspeciona o conteúdo) e o devolve inalterado em `POST /chat/croqui/confirmar`. Contém, entre
  outros campos internos do motor, `resumo_confirmacao` (frase curta em português, a única parte
  que o frontend de fato lê, para exibir "Entendi que você quer: ...").

### `POST /chat/croqui/confirmar`
- **Body:** `{ tenant_id, confirmado: bool, pendente: <objeto de pendente_confirmacao> }`
- **Se `confirmado: false`:** cancela, devolve `{ resposta: "Entendido! ...", imagem_url: null }`
  sem gastar nenhuma chamada.
- **Se `confirmado: true`:** modera o prompt visual (`validar_prompt_imagem`), checa
  `limite_imagens_dia` (`429` se excedido), executa a ferramenta de verdade (gera a imagem via
  gpt-image-1), incrementa o uso, e retoma a conversa até obter a resposta final (síntese/tabela
  de medidas).
- **Resposta:** `{ resposta: "string", imagem_url: "string | null" }`

## Conversas

### `GET /conversas?tenant_id=&usuario_id=`
### `POST /conversas` — `{ tenant_id, usuario_id }`
### `PATCH /conversas/{conversa_id}` — `{ tenant_id, usuario_id, novo_titulo?, mensagens? }`
### `DELETE /conversas/{conversa_id}?tenant_id=&usuario_id=`
### `GET /conversas/{conversa_id}/export?tenant_id=&usuario_id=&formato=txt|pdf`

Sem mudanças nesta fase — persistência em `tenant_data/conversas/{tenant_id}_{usuario_id}.json`,
protegida por `FileLock` desde a Fase 9.

## Documentos (Base de Conhecimento)

### `GET /documentos?tenant_id=`
### `POST /documentos/upload` — multipart, headers `X-Admin-Token`, limite 20MB
### `DELETE /documentos/{nome_arquivo}?tenant_id=` — headers `X-Admin-Token`

## Análise de Dados

### `POST /planilha/upload?tenant_id=&conversation_id=` — multipart, limite 20MB
- Gera e persiste o resumo estatístico por `conversation_id`, reaproveitado pelas próximas
  mensagens de chat no modo "Análise de Dados" na mesma conversa.

## Debug/Observabilidade (uso interno)

### `GET /debug/rag?tenant_id=`
- Último relatório de debug do pipeline RAG gerado neste processo (estado global do módulo, não
  segmentado por requisição — ver limitação documentada no próprio endpoint).

---

## Ferramentas do agente (referência rápida)

Schemas completos e handlers vivem em `agente_ferramentas.py` (fonte única de verdade — nunca
duplicados em `tenant_config.py`, que só referencia os nomes). Nenhuma recebe `tenant_id` ou
credenciais do modelo; esses valores vêm sempre do `ContextoExecucao` montado pelo backend.

| Ferramenta | Exige confirmação? | O que faz |
|---|---|---|
| `gerar_imagem_croqui` | Sim | Gera imagem via gpt-image-1 (OpenAI). |
| `gerar_ficha_tecnica` | Sim | Idem, mais instrução para montar a tabela de medidas na resposta final. |
| `buscar_documentos_internos` | Não | Busca semântica no RAG do tenant (mesmo pipeline do modo "Base de Conhecimento"). |
| `listar_documentos_disponiveis` | Não | Lista nomes de documentos indexados, sem gerar embeddings. |
| `consultar_resumo_planilha` | Não | Resumo estatístico da planilha enviada na conversa atual. |
| `consultar_unidades_senai` | Não | Endereço/telefone/e-mail das unidades do SENAI Goiás (dado estático). |

`web_search` (nativo da OpenAI, não é uma ferramenta do registry) é habilitado por modo via
`usar_web_search: True` em `tenant_config.py` — hoje: Tendências, Engenharia Têxtil, Assistente Geral.
