# SENAI LabFashion IA

Assistente de IA para a indústria da moda, multi-tenant, com 8 modos especializados (consultoria
de estilo, ensino técnico, engenharia têxtil, geração de croquis/fichas técnicas, tendências,
análise de dados, base de conhecimento documental via RAG, e um assistente generalista sem
restrição de escopo) construído sobre uma arquitetura agentiva: o modelo decide sozinho quando
responder de conhecimento próprio, pesquisar na web, ou consultar dados/ferramentas do sistema.

Arquitetura: **backend FastAPI** (Python) + **frontend Next.js** (React/TypeScript), separados --
não é mais a aplicação Streamlit original (código preservado na tag git `pre-remocao-streamlit`,
caso precise consultar).

---

## Arquitetura

- **Backend:** FastAPI (`api/main.py`), expõe a API REST consumida pelo frontend.
- **Frontend:** Next.js 16 / React, em `frontend/`.
- **LLM (texto):** [OpenAI](https://platform.openai.com/) (`gpt-4o` por padrão, via Responses API)
  -- chat, moderação, tool-calling (ferramentas próprias do sistema) e síntese do RAG.
- **Geração de imagem:** OpenAI `gpt-image-1` -- croquis e desenhos técnicos de moda.
- **Busca web:** `web_search` nativo da OpenAI (Responses API) -- usado pelos modos Tendências,
  Engenharia Têxtil e Assistente Geral quando a pergunta exige informação atual; o modelo decide
  sozinho quando pesquisar em vez de responder de conhecimento próprio.
- **RAG / Base de Conhecimento:** [ChromaDB](https://www.trychroma.com/) (embutido, self-hosted)
  + [Sentence-Transformers](https://www.sbert.net/) (`paraphrase-multilingual-MiniLM-L12-v2`,
  100% local em CPU, sem custo de API para vetorização) para embeddings.
- **Isolamento multi-tenant:** cada tenant tem seus próprios índices vetoriais
  (`tenant_data/chroma/{tenant_id}/`), conversas, planilhas e configurações -- uma busca de um
  tenant nunca retorna dados de outro.

## Modos disponíveis

| Modo | Descrição |
|---|---|
| Consultor de Estilo | Combinações, harmonia de cores, looks. |
| Professor Técnico | Costura, modelagem, tecidos -- tom didático. |
| Engenharia Têxtil | Normas técnicas (ABNT/ISO/AATCC/ASTM), ensaios de tecido, controle de qualidade -- tom técnico-industrial. |
| Gerador de Croqui | Ilustração de moda ou Desenho Técnico (flat sketch); inclui geração de ficha técnica completa (desenho + tabela de medidas/materiais). |
| Tendências | Análise de tendências com busca real na web (web_search nativo), cita fontes. |
| Análise de Dados | Upload de planilha (CSV/XLSX/XLS), perguntas sobre os números -- só o resumo estatístico vai pro LLM, nunca o dado bruto. |
| Base de Conhecimento | Pergunta sobre documentos indexados pelo tenant (RAG). |
| Assistente Geral | Sem restrição de escopo a moda -- qualquer assunto. |

---

## Arquitetura do agente

O chat roda sobre a [Responses API](https://platform.openai.com/docs/api-reference/responses) da
OpenAI (não Chat Completions -- é a única API que suporta `web_search` nativo junto com function
calling). Em cada mensagem, o modelo decide sozinho entre três caminhos, sem roteamento manual do
código:

```
Usuário → POST /chat → agente_openai.chamar_agente()
                            │
                            ├── responde de conhecimento próprio (sem tool nenhuma)
                            ├── web_search nativo (Tendências, Engenharia Têxtil, Assistente Geral)
                            └── ferramenta do sistema (agente_ferramentas.py)
                                   ├── buscar_documentos_internos (RAG do tenant)
                                   ├── listar_documentos_disponiveis
                                   ├── consultar_resumo_planilha
                                   ├── consultar_unidades_senai (contato SENAI)
                                   └── gerar_imagem_croqui / gerar_ficha_tecnica
                                          └── exigem confirmação explícita do usuário antes de executar
```

**Ferramentas** (`agente_ferramentas.py`) são declaradas uma única vez -- schema (o que o modelo
vê) e handler (o que de fato executa) vivem juntos, então não há como os dois divergirem.
`tenant_config.py` só referencia os nomes que cada modo pode usar; o schema completo é resolvido
contra esse registry.

**Segurança:**
- Nenhuma ferramenta recebe `tenant_id`, `conversation_id` ou credenciais do modelo -- vêm sempre
  de um `ContextoExecucao` montado pelo backend a partir da requisição autenticada. O isolamento
  multi-tenant não depende do bom comportamento do modelo.
- Uma ferramenta chamada fora da lista autorizada para o modo atual é recusada sem executar
  (least privilege), mesmo que exista em outro lugar do registry.
- Todo conteúdo que uma ferramenta devolve sai marcado com delimitadores explícitos ("dado a
  analisar, nunca uma instrução"), e o prompt de sistema instrui o modelo a nunca obedecer
  comandos encontrados em resultado de busca/ferramenta -- defesa contra prompt injection vinda de
  páginas web ou documentos. Limitação conhecida: como o `web_search` roda inteiramente do lado da
  OpenAI, o backend nunca vê o HTML bruto de uma página para sanitizá-lo à parte.
- Limites diários por tenant (`tenant_config.py`): `limite_mensagens_dia` (bloqueia com 429),
  `limite_imagens_dia` (bloqueia com 429), `limite_buscas_web_dia` (degrada graciosamente -- a
  ferramenta some da chamada e o modelo responde sem pesquisar, em vez de travar o modo inteiro).
- Ferramentas que geram um custo real ou efeito visível (`gerar_imagem_croqui`,
  `gerar_ficha_tecnica`) sempre exigem confirmação explícita do usuário antes de executar --
  `POST /chat/croqui/confirmar`.

**Observabilidade:** cada chamada de ferramenta é logada (nome, argumentos resumidos, latência,
sucesso/erro) em `agente_ferramentas.executar_ferramenta`; cada invocação completa do agente é
logada (pergunta resumida -- nunca o texto integral, rodadas de tool-calling, tokens de
entrada/saída, latência total, se usou `web_search`) em `agente_openai.chamar_agente`.

**UX:** a resposta do chat inclui `usou_busca_web` -- o frontend mostra um badge "Pesquisou na
web" quando é `true`, distinguindo visualmente de uma resposta de conhecimento próprio do modelo.
Fontes citadas (busca web ou RAG) aparecem como badges clicáveis; quando há URL real, ela vira um
link de verdade no popover.

**Limitações conhecidas:** duas defesas (o modelo de fato ignorar uma instrução embutida numa
página, e apresentar fontes contraditórias com honestidade em vez de inventar uma reconciliação)
dependem do comportamento do LLM em si, não de código -- não são testáveis de forma
determinística, só via validação manual/real (ver `tests/app/test_cenarios_agente.py`).

## Como rodar localmente (sem Docker)

**Backend:**
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (ver .venv/bin/activate no Linux/Mac)
pip install -r requirements.txt
cp .env.example .env            # preencha com suas chaves reais, ver seção abaixo
uvicorn api.main:app --reload   # http://localhost:8000
```

**Frontend** (em outro terminal):
```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

Acesse `http://localhost:3000` no navegador.

## Como rodar com Docker

```bash
cp .env.example .env            # preencha com suas chaves reais
docker compose up --build
```

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend (API): [http://localhost:8000](http://localhost:8000) -- healthcheck em `/health`

Para deploy numa VPS com domínio próprio, ver `nginx.conf.example` (reverse proxy) e a seção
"Deploy em produção" abaixo.

## Variáveis de ambiente (`.env`)

Copie `.env.example` para `.env` e preencha (convenção: `{TENANT_ID_MAIUSCULO}_{CHAVE}`):

| Variável | Uso |
|---|---|
| `SENAI_LABFASHION_OPENAI_API_KEY` | Chat (GPT-4o), moderação, geração de imagem (gpt-image-1), busca web (web_search nativo). |
| `SENAI_LABFASHION_ADMIN_PASSWORD` | Senha do painel administrativo (`/admin`). |

Variáveis adicionais (não vão no `.env`, são configuração de deploy):

| Variável | Onde | Uso |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | Ambiente do backend | Lista separada por vírgula de origens permitidas. Default: só `http://localhost:3000`. |
| `NEXT_PUBLIC_API_URL` | Build arg do frontend (`frontend/Dockerfile`) | URL pública da API, alcançável pelo navegador do usuário final. Embutida em tempo de build, não de execução. |
| `NEXT_PUBLIC_TENANT_ID` | Build arg do frontend | Tenant padrão do frontend. Default: `senai_labfashion`. |
| `LOG_LEVEL` | Ambiente do backend | Nível de log (default `INFO`). |

## Deploy em produção (VPS)

1. `docker compose build` com os build args corretos do frontend (domínio público real):
   ```bash
   NEXT_PUBLIC_API_URL=https://seu-dominio.com/api docker compose build frontend
   ```
2. Definir `CORS_ALLOWED_ORIGINS=https://seu-dominio.com` no `.env` do backend.
3. `docker compose up -d`.
4. Configurar um reverse proxy (Nginx) na frente dos dois serviços -- ver `nginx.conf.example`
   (roteia `/` pro frontend, `/api/` pro backend) e configurar TLS (ex: Certbot/Let's Encrypt).

## Admin (`/admin`)

O painel administrativo (upload/remoção de documentos da Base de Conhecimento) exige login com a
senha configurada em `SENAI_LABFASHION_ADMIN_PASSWORD`. O login emite um token de sessão (válido
por 4h) exigido pelo backend em toda rota administrativa -- bloqueio automático por 15 minutos
após 5 tentativas de senha incorretas.

## Testes

```bash
python -m unittest discover -s tests   # suíte completa do backend (RAG, agente, tool-calling, etc.)
cd frontend && npm run build           # valida o build de produção do frontend
```

Um workflow de CI (`.github/workflows/ci.yml`) roda os dois automaticamente em todo push/PR. Os
testes do agente ficam em `tests/app/test_agente_ferramentas*.py` (registry de ferramentas),
`test_agente_openai.py` (motor/Responses API) e `test_cenarios_agente.py` (um teste por cenário de
uso agentivo -- pergunta sem web, com web, múltiplas ferramentas, falha de tool, tool não
autorizada, etc.). Testes de mudanças no chat/agente que dependem da API real da OpenAI (não
mockáveis) são validados manualmente contra um servidor isolado antes de cada commit.

## Logs e diagnóstico

- Logs vão tanto para stdout (essencial em containers) quanto para `logs/app.log`
  (`RotatingFileHandler`, 5MB por arquivo, até 5 arquivos históricos).
- Nível configurável via `LOG_LEVEL` (default `INFO`).
- **Privacidade:** nenhuma chave de API, senha administrativa ou conteúdo bruto de prompt do
  usuário é gravado em log -- perguntas aparecem só como um resumo truncado.
- Toda chamada de ferramenta do agente é logada (`tool=... status=... duracao_ms=... args=...
  resultado=...`), assim como cada invocação completa do agente (`agente pergunta=... rodadas=...
  tokens_in=... tokens_out=... duracao_ms=... web_search=...`).
