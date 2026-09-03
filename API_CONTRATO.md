# Contrato da API (Fase 3, Passo 15)

Rascunho dos endpoints mínimos para extrair a lógica de negócio de `app.py` para uma API própria
(FastAPI, Passo 16+), permitindo depois construir o front-end em React/Next.js sobre ela. Cada
endpoint mapeia para função(ões) Python já existentes e testadas — nenhuma lógica nova aqui, só a
casca de transporte HTTP.

Convenção: `tenant_id` é sempre obrigatório (path, query ou body conforme o verbo) — a API continua
multi-tenant mesmo com uso single-tenant na prática hoje.

## Autenticação/Admin

### `POST /admin/login`
- **Body:** `{ tenant_id, senha }`
- **Lógica:** compara `senha` com `obter_secret_tenant(tenant_id, "ADMIN_PASSWORD")` (app.py:45).
- **Resposta:** `{ autorizado: bool }` (ou token/sessão, a definir na Fase 3 quando houver sessão HTTP
  real — hoje é só um gate de UI via `st.session_state`, sem token).

## Configuração do Tenant

### `GET /config/tenant?tenant_id=`
- **Lógica:** `carregar_config_tenant(tenant_id, TENANT_CONFIG[tenant_id])` (app.py:82).
- **Resposta:** config mesclada (branding, prompts, modos, cores).

### `PUT /config/tenant`
- **Body:** `{ tenant_id, dados_custom }`
- **Lógica:** `salvar_config_tenant(tenant_id, dados_custom)` (app.py:120).

## Chat

### `POST /chat`
- **Body:** `{ tenant_id, conversation_id, modo, perfil_usuario, mensagem }`
- **Lógica por `modo`** (espelha o dispatch hoje em `app.py`, dentro de `with tab_assistente:`):
  - **"Base de Conhecimento":** `buscar_contexto_relevante(tenant_id, mensagem, top_k=10,
    conversation_id=conversation_id)` (rag_manager.py:1016) → `montar_prompt_final(chunks,
    mensagem)` (rag_manager.py, Passo 14) → `client.chat.completions.create(model=GROQ_MODEL, ...)`.
  - **"Análise de Dados":** `responder_pergunta_sobre_dados(client, pergunta, resumo_estatistico,
    prompt_sistema, tenant_id)` (analise_dados.py:328). **Atenção:** hoje `resumo_estatistico` vem de
    `st.session_state.resumo_estatistico_atual` (populado ao fazer upload da planilha) — como a API é
    stateless entre requisições, esse resumo precisa ser persistido por `conversation_id` (ex.: campo
    novo em `tenant_data/conversas/` ou cache separado) antes deste endpoint funcionar sem Streamlit.
    Ajuste necessário na Fase 3, não um bloqueador do contrato em si.
  - **"Gerador de Croqui":** `chamar_agente(client, agente_config, messages_for_api)` (app.py:712),
    que internamente despacha para `executar_ferramenta_local()` (app.py:699) →
    `chamar_api_geracao_imagem()` (app.py:691) quando o modelo aciona a tool de geração de imagem;
    passa por `validar_prompt_imagem()` (moderacao.py:28) antes de gerar.
  - **Outros modos custom** (definidos em `tenant_config.py`): chamada direta ao Groq com
    `CUSTOM_PROMPT` (`config['base_prompt'] + prompt_modo + contexto_perfil`), sem RAG.
  - Em todos os casos: `incrementar_uso(tenant_id, "mensagens")` (usage_tracker.py:45) e checagem
    prévia de `verificar_limite(...)` (usage_tracker.py:66); cache opcional via
    `obter_resposta_cacheada`/`salvar_resposta_cache` (resposta_cache.py).
- **Resposta:** `{ resposta, fontes_consultadas, trechos_consultados, imagem_url? }`.

## Conversas

### `GET /conversas?tenant_id=&usuario_id=`
- **Lógica:** `carregar_conversas(tenant_id, usuario_id)` (conversas_manager.py:24).

### `POST /conversas`
- **Body:** `{ tenant_id, usuario_id }`
- **Lógica:** `criar_nova_conversa()` (conversas_manager.py:57) + `salvar_conversas(...)`
  (conversas_manager.py:45). Título inicial via `gerar_titulo_conversa(primeira_mensagem)`
  (conversas_manager.py:71) assim que a primeira mensagem chegar.

### `PATCH /conversas/{conversa_id}`
- **Body:** `{ tenant_id, usuario_id, novo_titulo }`
- **Lógica:** `renomear_conversa(conversas, conversa_id, novo_titulo)` (conversas_manager.py:86) +
  `salvar_conversas(...)`.

### `DELETE /conversas/{conversa_id}`
- **Lógica:** não existe função dedicada hoje — `app.py` (~linha 915) filtra a lista em memória e
  chama `salvar_conversas(...)` com a lista sem o item removido. Replicar esse padrão no endpoint
  (carregar lista, filtrar, salvar) em vez de criar uma função nova — comportamento simples o
  suficiente para não precisar de uma função dedicada em `conversas_manager.py`.

### `GET /conversas/{conversa_id}/export?formato=pdf|txt`
- **Lógica:** `formatar_conversa_txt(messages, ...)` (app.py:166) ou `gerar_conversa_pdf(messages,
  ...)` (app.py:197, via `fpdf2`).

## Documentos (Base de Conhecimento)

### `GET /documentos?tenant_id=`
- **Lógica:** `listar_documentos_indexados(tenant_id)` (rag_manager.py).

### `POST /documentos/upload`
- **Body:** multipart (`tenant_id`, arquivo)
- **Lógica:** `extrair_documento(stream, nome_arquivo, extensao)` (rag_manager.py/document_extractors.py)
  → `indexar_documento(tenant_id, nome_arquivo, unidades_extraidas, dados_tabulares=...)`
  (rag_manager.py:864 região). Requer checagem de `EXTENSOES_SUPORTADAS` antes de aceitar o arquivo.

### `DELETE /documentos/{nome_arquivo}?tenant_id=`
- **Lógica:** `remover_documento(tenant_id, nome_arquivo)` (rag_manager.py).

## Análise de Dados (upload de planilha)

### `POST /planilha/upload`
- **Body:** multipart (`tenant_id`, `conversation_id`, arquivo)
- **Lógica:** `carregar_planilha(arquivo, tenant_id)` (analise_dados.py:43) →
  `gerar_resumo_estatistico(df)` (analise_dados.py:195). **Mesma observação do endpoint `/chat`:** o
  resumo resultante precisa ser persistido por `conversation_id` para ser reaproveitado nas
  perguntas subsequentes daquela conversa (hoje vive só em `st.session_state`).

## Debug/Observabilidade (opcional, uso interno)

### `GET /debug/rag?tenant_id=`
- **Lógica:** `obter_ultimo_rag_debug()` / `formatar_bloco_debug_rag()` (rag_manager.py) — expõe o
  último relatório de debug do pipeline RAG. Só relevante para uma futura tela de administração; não
  é prioridade da Fase 4 (front-end React).

---

## Observações que afetam a ordem de implementação (Passo 16+)

1. **Estado hoje vive em `st.session_state`, a API precisa persistir isso em disco/DB:**
   `resumo_estatistico_atual` (Análise de Dados) é o único caso que exige uma mudança real de
   arquitetura (persistir por conversa) — todo o resto (conversas, documentos, config) já persiste em
   `tenant_data/` e só precisa de uma casca HTTP em cima.
2. **`/chat` é o endpoint mais complexo** (Passo 17 do roadmap) por despachar para 3 fluxos internos
   diferentes conforme o `modo` — implementar primeiro só o caminho "Base de Conhecimento" (mais
   simples, já 100% stateless) antes de extrair "Gerador de Croqui" e "Análise de Dados".
3. **Nenhuma função de negócio precisa ser reescrita** — todas as listadas acima já existem e têm
   cobertura de teste (RAG) ou são triviais o suficiente (conversas, config) para escrever teste
   junto com o endpoint.
