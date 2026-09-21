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
- **RAG / Base de Conhecimento:** [ChromaDB](https://www.trychroma.com/) (embutido, self-hosted,
  `hnsw:space="cosine"` explícito) + [Sentence-Transformers](https://www.sbert.net/)
  (`paraphrase-multilingual-MiniLM-L12-v2`, 100% local em CPU, sem custo de API) para embeddings.
  Busca híbrida: vetorial + BM25 próprio (`bm25_index.py`) fundidos por Reciprocal Rank Fusion,
  reranking heurístico configurável por tenant, e um segundo salto que segue códigos alfanuméricos
  citados no trecho-âncora até outro documento (ex.: liga uma peça do manual ao preço dela no
  catálogo). Perguntas de agregação/filtro/listagem sobre planilhas indexadas (`AVG`, `SUM`,
  `DISTINCT`, superlativos) são resolvidas deterministicamente por um motor tabular
  (`tabular_query_engine.py`), nunca por soma feita pelo LLM. Medido continuamente contra um
  golden set sintético versionado (`rag_golden_set.py`, custo zero de API) — ver
  `RAG_BASELINE_FASE13.md` para a metodologia e o histórico de medições.
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

**Modo inicial (Fase 14, Bloco U):** quem nunca escolheu um perfil começa em "Consultor de
Estilo" (`MODO_PADRAO_SEM_PERFIL`, `frontend/src/lib/modos.ts`) -- não depende de nenhum documento
indexado, ao contrário de "Base de Conhecimento", que era o ponto de partida antigo e respondia
"não encontrei nos documentos" para um app recém-instalado. Quem já escolheu um perfil numa visita
anterior volta direto no modo padrão daquele perfil (`MODO_PADRAO_POR_PERFIL`,
`frontend/src/lib/perfis.ts`) a cada novo carregamento, não só no momento da escolha.

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
                                   ├── buscar_documentos_internos (RAG do tenant; Consultor de
                                   │     Estilo, Professor Técnico, Engenharia Têxtil, Tendências
                                   │     e Assistente Geral)
                                   ├── listar_documentos_disponiveis (mesmos modos acima)
                                   ├── consultar_resumo_planilha (Tendências, Assistente Geral --
                                   │     cruza a planilha da empresa com tendência de mercado)
                                   ├── consultar_unidades_senai (contato SENAI; só Assistente Geral)
                                   ├── gerar_imagem_croqui (gera imagem)
                                   └── gerar_ficha_tecnica (cria ficha real em /fichas -- não gera imagem)
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
  `usage_tracker.verificar_limite` é fail-**closed** (Fase 14, Bloco S, Task 3): se o contador de
  uso não puder ser lido (arquivo corrompido), o limite é tratado como excedido em vez de
  liberado -- o oposto do comportamento anterior, que abria uma licença ilimitada até alguém
  notar o erro no log.
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

## Gerador de fichas técnicas (`/fichas`)

Área dedicada, fora do chat, para gerar a ficha técnica de uma peça como documento Word/PDF fiel a
um template real -- distinta da ferramenta `gerar_ficha_tecnica` do chat (que só devolve imagem +
tabela markdown na conversa, sem produzir arquivo nenhum). Fluxo:

```
Texto livre → extração estruturada (Structured Outputs) → verificação de proveniência
    → revisão editável (tabelas dinâmicas, alertas) → desenho técnico opcional (com aprovação)
    → preenche templates/ficha_tecnica_v1.docx (docxtpl) → exporta .docx / .pdf (LibreOffice)
```

- **Fidelidade ao template.** O `.docx` de 3 páginas é aberto e preenchido, nunca reconstruído --
  `docxtpl` renderiza o `document.xml` original como template Jinja, preservando margens, estilos e
  células mescladas por construção. `scripts/anotar_template.py` documenta e reproduz a anotação
  (placeholders + tabelas dinâmicas) caso uma v2 do formulário em branco chegue algum dia.
- **Não-invenção garantida por código, não por prompt.** Cada campo carrega `origem`/`trecho`; um
  verificador determinístico (`fichas_verificacao.py`) confirma que o trecho é substring real do
  texto do usuário, e uma allowlist de campos não-inferíveis (preço, fornecedor, composição, nº de
  moldes, data, designer...) é **zerada pelo código** se a origem não for `FORNECIDO` -- o prompt é
  só reforço, a garantia é mecânica.
- **Desenho técnico opcional** (`gpt-image-1`), versionado (v1, v2, ...) e sujeito a aprovação
  explícita do usuário -- só a versão aprovada entra no documento final. Como o modelo não tem
  seed/determinismo, regenerar produz uma peça nova, não uma correção pontual: instruções de ajuste
  são acumuladas entre versões (`fichas_desenho.acumular_instrucao`).
- **PDF via LibreOffice headless** (`fichas_pdf.py`) -- único caminho de conversão docx→PDF, tanto
  em dev quanto na imagem Docker; requer `LIBREOFFICE_PATH` ou o executável no `PATH` (ver seção de
  variáveis de ambiente abaixo). Sem ele, as rotas de PDF devolvem `501` com instrução do que fazer.
- **Logo da empresa** (`/branding/logo`) cadastrado uma vez por tenant e reaproveitado em toda
  ficha, redimensionado proporcionalmente (nunca deformado, nunca estoura a célula do cabeçalho).
- **"Nova ficha" oferece descrever a peça** (Fase 14, Bloco F): a extração por texto livre já
  existia na API desde sempre (`POST /fichas` com `texto_origem`), mas só era alcançável pelo
  atalho `gerar_ficha_tecnica` do chat -- a tela `/fichas` sempre criava em branco. Agora o botão
  "Nova ficha" pergunta primeiro se a pessoa quer descrever a peça (chamada real à IA, preenche os
  campos) ou começar em branco (sem custo nenhum).

Ver `API_CONTRATO.md` (seções "Fichas técnicas" e "Logo da empresa") para o contrato completo das
rotas, e `tests/app/test_fichas_cenarios_e2e.py` para os cenários de ponta a ponta (combinações de
logo/desenho/grade/custos) que amarram o documento final ao template.

A ferramenta `gerar_ficha_tecnica` do modo "Gerador de Croqui" (chat) é um **atalho** para esta
área, não um caminho paralelo (Fase 12): ao confirmar, ela cria uma ficha de verdade a partir da
mensagem do usuário (mesmo pipeline de extração de `POST /fichas`) e devolve um link para
`/fichas/{id}` -- em vez do comportamento anterior (gerar uma imagem solta + pedir ao modelo para
redigir uma tabela markdown que desaparecia ao fechar o chat).

## Galeria de croquis (`/croquis`, Fase 14, Bloco G)

Todo croqui gerado no modo "Gerador de Croqui" (imagem, não ficha técnica) é persistido em disco
(`croquis_repo.py`) assim que a geração termina -- antes, existia só como data URI dentro do
histórico de uma conversa específica, perdido se ela fosse excluída. A tela `/croquis`, acessível
pelo cabeçalho do chat, lista a galeria completa com miniatura, estilo, o resumo em português e a
data de criação; excluir um croqui é ação administrativa (mesma senha de admin de excluir ficha).
Conversas antigas, persistidas antes desta fase, continuam funcionando normalmente -- a mensagem
guarda a data URI base64 de sempre, já que nunca tiveram um `croqui_id`.

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
| `SENAI_LABFASHION_ACCESS_PASSWORD` | Senha única de acesso ao app inteiro (Fase 14) -- opcional; sem ela, o app fica aberto como sempre (uso em desenvolvimento local). |
| `SENAI_LABFASHION_ADMIN_PASSWORD` | Senha do painel administrativo (`/admin`). |

Variáveis adicionais (não vão no `.env`, são configuração de deploy):

| Variável | Onde | Uso |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | Ambiente do backend | Lista separada por vírgula de origens permitidas. Default: só `http://localhost:3000`. |
| `NEXT_PUBLIC_API_URL` | Build arg do frontend (`frontend/Dockerfile`) | URL pública da API, alcançável pelo navegador do usuário final. Embutida em tempo de build, não de execução. |
| `NEXT_PUBLIC_TENANT_ID` | Build arg do frontend | Tenant padrão do frontend. Default: `senai_labfashion`. |
| `LOG_LEVEL` | Ambiente do backend | Nível de log (default `INFO`). |
| `LIBREOFFICE_PATH` | Ambiente do backend | Caminho do executável do LibreOffice, para as rotas de PDF de fichas técnicas (`/fichas/{id}/pdf`, `/fichas/{id}/preview`). Opcional -- sem ele, o backend procura no `PATH`/locais padrão; se não encontrar, as rotas de PDF devolvem `501` (rotas de `.docx` continuam funcionando normalmente). |

## Deploy em produção (VPS)

1. `docker compose build` com os build args corretos do frontend (domínio público real):
   ```bash
   NEXT_PUBLIC_API_URL=https://seu-dominio.com/api docker compose build frontend
   ```
2. Definir `CORS_ALLOWED_ORIGINS=https://seu-dominio.com` no `.env` do backend.
3. `docker compose up -d`.
4. Configurar um reverse proxy (Nginx) na frente dos dois serviços -- ver `nginx.conf.example`
   (roteia `/` pro frontend, `/api/` pro backend) e configurar TLS (ex: Certbot/Let's Encrypt).

## Senha única de acesso (Fase 14)

O app inteiro (não só `/admin`) pode ser protegido por uma senha compartilhada, configurada em
`SENAI_LABFASHION_ACCESS_PASSWORD`. Sem cadastro de usuário final por design (ver decisão da Fase
9), esta é a porta de entrada: uma senha, não um login por pessoa -- fecha o acesso a quem está
fora da organização, mas não isola um colega do outro dentro dela. Sem a variável definida, o app
fica aberto como sempre (comportamento de desenvolvimento local). O login (`PortaoDeAcesso.tsx`,
que envolve todas as páginas em `layout.tsx`) emite um token válido por 30 dias, guardado no
navegador -- bloqueio automático de 15 minutos por IP após 5 tentativas incorretas.

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

Os testes do gerador de fichas técnicas ficam em `tests/app/test_fichas_*.py` -- um arquivo por
módulo (modelo, validação, extração, verificação de proveniência, repositório, template, docx,
logo, desenho, pdf) mais `test_api_fichas.py` (rotas HTTP) e `test_fichas_cenarios_e2e.py`
(cenários de ponta a ponta: combinações de logo/desenho/grade/custos que só aparecem quando várias
peças do sistema se juntam no mesmo documento). Extração e geração de imagem são sempre mockadas;
os testes que exigem o LibreOffice de verdade (conversão PDF, contagem de página) se pulam sozinhos
via `skipUnless` quando ele não está instalado no ambiente -- o CI não o tem.

Os testes do RAG ficam em `tests/rag/` -- unitários por peça (resolução de coluna tabular, fusão
BM25/RRF, salto por entidade, pareamento fonte/trecho) e `test_baseline_regressao.py`, que roda o
golden set completo (`rag_golden_set.py`, custo zero de API) e falha se qualquer métrica de
recall/nDCG/MRR, taxa de abstenção ou taxa de acerto computado regredir contra
`rag_baseline_fase13.json` -- **por categoria**, não só na média (ver `RAG_BASELINE_FASE13.md`).
Uma melhoria de verdade sobe essa régua conscientemente via
`python scripts/medir_baseline_rag.py --rotulo "..." --forcar`, nunca por edição manual do JSON.
Diretórios de tenant de teste ficam em `tenant_data/{chroma,tabular}/teste_*` -- `scripts/limpar_tenants_orfaos.py`
lista (e, com `--forcar`, remove) qualquer diretório de tenant nessas pastas que não seja
`senai_labfashion` nem esteja em uso por um teste rodando.

## Logs e diagnóstico

- Logs vão tanto para stdout (essencial em containers) quanto para `logs/app.log`
  (`RotatingFileHandler`, 5MB por arquivo, até 5 arquivos históricos).
- Nível configurável via `LOG_LEVEL` (default `INFO`).
- **Privacidade:** nenhuma chave de API, senha administrativa ou conteúdo bruto de prompt do
  usuário é gravado em log -- perguntas aparecem só como um resumo truncado.
- Toda chamada de ferramenta do agente é logada (`tool=... status=... duracao_ms=... args=...
  resultado=...`), assim como cada invocação completa do agente (`agente pergunta=... rodadas=...
  tokens_in=... tokens_out=... duracao_ms=... web_search=...`).
- Toda busca RAG loga uma linha resumida sempre ativa (`rag_query_summary tenant=... route=...
  tabular_attempted=... chunks=... tempo_ms=...`), independente do modo debug verboso
  (`RAG_DEBUG`/`GET /debug/rag`, que exige `X-Admin-Token` do próprio tenant e nunca devolve o
  debug de outro).
