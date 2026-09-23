# Contrato da API

Referência dos endpoints REST expostos por `api/main.py` (FastAPI), consumidos pelo frontend
Next.js via `frontend/src/lib/api.ts`. Documenta o contrato **atual** — não um plano; para a
arquitetura de IA por trás de `/chat`, ver a seção "Arquitetura do agente" no `README.md`.

Convenção: `tenant_id` é sempre obrigatório. Multi-tenant na estrutura, uso single-tenant
(`senai_labfashion`) na prática hoje.

## Senha única de acesso (Fase 14, Bloco S)

Camada de acesso ao app **inteiro**, separada da autenticação de admin abaixo — não é login por
pessoa, é uma porta fechada para quem não sabe a senha compartilhada da organização.

### `POST /acesso/login`
- **Body:** `{ senha }`
- **Lógica:** compara com `SENAI_LABFASHION_ACCESS_PASSWORD` via `hmac.compare_digest`; bloqueio
  de 15min após 5 tentativas incorretas **por IP** (diferente do admin, que hoje bloqueia por
  tenant — ver nota da Task 2). Sem a variável de ambiente definida, o gate fica inteiramente
  desligado e a rota sempre autoriza (comportamento de desenvolvimento local).
- **Resposta:** `{ autorizado: bool, token: string | null }` — `token` é opaco, válido por 30
  dias, exigido no header `X-Access-Token` em toda rota do backend, **exceto**, e só nestes
  métodos (Fase 15, V1 — a isenção é por `(método, caminho)`, nunca só por caminho):
  - `GET /health`, `POST /acesso/login`, `GET /branding/logo`;
  - `GET /fichas/{id}/preview`, `GET /fichas/{id}/docx`, `GET /fichas/{id}/pdf`,
    `GET /fichas/{id}/desenho/{versao}` (versão precisa ser numérica), `GET /conversas/{id}/export`,
    `GET /croquis/{id}/imagem`.

  Essas rotas servem um arquivo para consumo direto do navegador (`<img src>`, `<a href>`,
  `<iframe src>`), que não anexa headers customizados — ficam de fora do gate por necessidade
  técnica, não por descuido. São sempre leitura de um recurso cujo identificador (UUID de ficha)
  já não é adivinhável. **`POST /fichas/{id}/desenho/importar-croqui` não está nesta lista** —
  antes da Fase 15 estava, por acidente: a isenção testava só o caminho, e essa rota (que escreve)
  casava com o mesmo padrão da leitura da imagem.

## Autenticação/Admin

### `POST /admin/login`
- **Body:** `{ tenant_id, senha }`
- **Lógica:** compara `senha` com `obter_secret_tenant(tenant_id, "ADMIN_PASSWORD")` via
  `hmac.compare_digest` (constant-time); bloqueio de 15min após 5 tentativas incorretas **por IP**
  (corrigido na Fase 14, Bloco S, Task 2 -- era por `tenant_id`, uma string pública, então
  qualquer um negava o acesso do admin legítimo só errando a senha 5 vezes de propósito).
- **Resposta:** `{ autorizado: bool, token: string | null }` — `token` é opaco, válido por 4h,
  exigido no header `X-Admin-Token` nas rotas administrativas abaixo.

## Configuração do Tenant

### `GET /config/tenant?tenant_id=`
- **Resposta:** config mesclada (branding, prompts, modos, limites diários, cores) — não exige auth.

### `PUT /config/tenant`
- **Headers:** `X-Admin-Token`
- **Body:** `{ tenant_id, dados_custom }`

### `GET /uso?tenant_id=` (Fase 14, Bloco U, Task 9)
- **Resposta:** uso do dia por categoria, para o frontend mostrar "restam N mensagens hoje" antes
  do limite chegar como erro na hora de enviar — não exige auth (mesmo padrão de `GET
  /config/tenant`, não expõe nada sensível).
  ```jsonc
  {
    "data": "2026-09-21",
    "categorias": {
      "mensagens": { "usado": 5, "limite": 200, "restante": 195 },
      "imagens": { "usado": 0, "limite": 30, "restante": 30 },
      "buscas_web": { "usado": 2, "limite": 50, "restante": 48 },
      "fichas": { "usado": 0, "limite": 30, "restante": 30 }
    }
  }
  ```
  Usa `carregar_uso_do_dia` (versão tolerante do `usage_tracker`), não a versão estrita usada por
  `verificar_limite` — um erro de leitura aqui vira "0 usado", nunca um 500 numa rota só de leitura.

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
    "usou_busca_web": true | false,    // distingue "respondeu de conhecimento próprio" de
                                        // "pesquisou antes de responder" -- só relevante nos
                                        // modos com usar_web_search habilitado
    "busca_web_desligada_por_cota": true | false  // (Fase 14, Bloco U, Task 9) true quando o modo
                                        // usa busca web mas o limite diário de buscas_web já foi
                                        // atingido -- esta resposta saiu sem pesquisar; antes essa
                                        // degradação era só um log de servidor, invisível pro
                                        // usuário
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
- **Se `confirmado: true`, o caminho depende de `pendente.nome_ferramenta`:**
  - **`gerar_imagem_croqui`:** modera o prompt visual (`validar_prompt_imagem`), checa
    `limite_imagens_dia` (`429` se excedido), executa a ferramenta de verdade (gera a imagem via
    gpt-image-1), incrementa o uso, e retoma a conversa até obter a resposta final (síntese em
    texto). **Resposta:** `{ resposta: "string", imagem_url: "string | null", croqui_id: "string | null" }`
    — `croqui_id` (Fase 14, Bloco G, Task 14) é o id na galeria (`GET /croquis`), persistido a
    partir da mesma data URI que `imagem_url` traz; gravação é *best-effort* (a imagem já foi
    gerada e cobrada antes deste ponto) — `null` se a escrita em disco falhar, sem afetar o
    resto da resposta.
  - **`gerar_ficha_tecnica` (Fase 12):** checa `limite_fichas_dia` (`429` se excedido) e cria uma
    ficha real — mesmo pipeline de `POST /fichas` com `texto_origem` (extração estruturada +
    verificação de proveniência + persistência), usando a mensagem que o usuário digitou nesta
    conversa (não um prompt reformulado pelo modelo). Não gera imagem nenhuma; é um atalho para a
    área `/fichas`, não um substituto dela. **Resposta:**
    `{ resposta: "string", imagem_url: null, ficha_id: "string | null", redirecionar_para: "string | null" }`
    — `redirecionar_para` é o caminho `/fichas/{ficha_id}` para o frontend oferecer um link; ambos
    vêm `null` se a extração falhar (erro relatado só na `resposta`, mesmo padrão de falha de
    `gerar_imagem_croqui`).

## Conversas

### `GET /conversas?tenant_id=&usuario_id=`
### `POST /conversas` — `{ tenant_id, usuario_id }`
### `PATCH /conversas/{conversa_id}` — `{ tenant_id, usuario_id, novo_titulo?, mensagens? }`
### `DELETE /conversas/{conversa_id}?tenant_id=&usuario_id=`
### `GET /conversas/{conversa_id}/export?tenant_id=&usuario_id=&formato=txt|pdf`

Persistência em `tenant_data/conversas/{tenant_id}_{usuario_id}.json`, protegida por `FileLock`
desde a Fase 9. **Todas as 5 rotas validam `tenant_id` (404 se desconhecido) e `usuario_id`
(400 se não for um UUID) antes de tocar em disco** (Fase 15, V2) — antes só `GET .../export`
validava `tenant_id`, e `usuario_id` (que vem do `localStorage` do navegador, controle total do
cliente) nunca era validado em rota nenhuma, indo cru para o nome do arquivo. `tenant_id` não
precisa ser UUID (é um slug de configuração) e é sanitizado por allowlist de caracteres, não
rejeitado.

## Documentos (Base de Conhecimento)

### `GET /documentos?tenant_id=`
### `POST /documentos/upload` — multipart, headers `X-Admin-Token`, limite 20MB
- Extração e indexação (embeddings) rodam em thread separada (`asyncio.to_thread`, Fase 13, Task
  15) -- um upload grande não trava outras requisições da API enquanto indexa.
### `DELETE /documentos/{nome_arquivo}?tenant_id=` — headers `X-Admin-Token`

## Análise de Dados

### `POST /planilha/upload?tenant_id=&conversation_id=` — multipart, limite 20MB
- Gera e persiste o resumo estatístico por `conversation_id`, reaproveitado pelas próximas
  mensagens de chat no modo "Análise de Dados" na mesma conversa.
- `conversation_id` precisa ser um UUID (400 caso contrário) — validado antes do parsing da
  planilha, não depois (Fase 15, V2: o valor virava parte de um nome de arquivo sem checagem
  nenhuma). O modo "Análise de Dados" do chat aplica a mesma validação ao ler o resumo.
- Mesmo motivo do upload de documentos acima: parsing e resumo estatístico rodam fora do event
  loop (Fase 13, Task 15).

## Fichas técnicas (`/fichas`, Fase 11)

Área dedicada, fora do chat, que preenche um template `.docx` real (`templates/ficha_tecnica_v1.docx`)
e exporta Word/PDF -- ver a seção "Gerador de fichas técnicas" no `README.md` para a arquitetura por
trás. Distinta da ferramenta `gerar_ficha_tecnica` do chat (só devolve imagem + tabela markdown na
conversa, não produz documento nenhum).

### `POST /fichas` — `{ tenant_id, texto_origem? }`
- Sem `texto_origem`: cria uma ficha em branco (`RASCUNHO`), sem chamada de API.
- Com `texto_origem`: checa `limite_fichas_dia` (`429` se excedido) → extração estruturada
  (`fichas_extracao`, Structured Outputs, chamada real de API) → verificação de proveniência
  (`fichas_verificacao`, zera campos não-inferíveis sem origem `FORNECIDO`) → persiste com status
  `EM_REVISAO`.
- Semeia `ficha["precificacao"]` com `TENANT_CONFIG[...]["precificacao_padrao"]` (Fase 14, Bloco P,
  Task 19) — zerado por padrão, editável depois por ficha via `PUT /fichas/{id}` normal.
- **Resposta** (mesmo envelope em toda rota que devolve uma ficha):
  ```jsonc
  {
    "ficha": { ..., "precificacao": { "imposto_percentual", "comissao_percentual", "margem_lucro_percentual" } },
    "alertas": [ { "codigo", "severidade", "campo", "mensagem" }, ... ],
    "precificacao_calculada": {
      "calculavel": true, "motivo": "",
      "preco_sugerido": 181.82, "custo_total": 100.0,
      "categorias_informadas": { "aviamentos": 100.0 }, "categorias_ausentes": ["tecidos", "..."],
      "parametros": { "imposto_percentual": 10, "comissao_percentual": 15, "margem_lucro_percentual": 20 },
      "percentual_total": 45.0, "divisor": 0.55
    }
  }
  ```
  `alertas` e `precificacao_calculada` são recalculados a cada leitura/escrita
  (`fichas_validacao.validar_ficha`, `fichas_precificacao.calcular`) — nunca um snapshot congelado.
  `precificacao_calculada` usa markup **divisor** (`preco = custo / (1 - percentual_total/100)`),
  correto quando imposto/comissão/margem incidem sobre o preço de venda, não sobre o custo.
  `calculavel: false` (com `motivo`) quando nenhum custo foi informado ainda, ou quando os
  percentuais somam 100% ou mais (denominador ≤ 0) — nunca uma exceção nem um preço negativo.

### `GET /fichas?tenant_id=`
Lista o histórico leve (id, ref, nome, status, datas) — `fichas_repo`, sem carregar o JSON completo
de cada ficha.

### `GET /fichas/{ficha_id}?tenant_id=`
### `PUT /fichas/{ficha_id}` — `{ tenant_id, ficha, atualizado_em_esperado? }`
- `atualizado_em_esperado` é o timestamp que o cliente tinha ao abrir a ficha para edição;
  divergência do valor salvo em disco (edição concorrente em outra aba/sessão) devolve `412`.
- O `id` do path é sempre a fonte de verdade — um `id` divergente no corpo é ignorado.

### `POST /fichas/{ficha_id}/duplicar` — `{ tenant_id }`
Cópia com novo `id`, mesma finalidade de "vou usar como base para outro modelo". Não herda a
aprovação da original (nem o desenho/documentos) — a cópia nasce `RASCUNHO`.

### `POST /fichas/{ficha_id}/aprovar` — `{ tenant_id, aprovada_por, atualizado_em_esperado, observacao? }` (Fase 14, Bloco AP)
Registra a aprovação e leva o status para `APROVADA`. É um **registro nominal, não uma assinatura
digital**: guarda o nome que a pessoa digitou, sem autenticação por trás (decisão travada com o
usuário) — a UI precisa rotulá-lo assim pelo mesmo motivo.

- `atualizado_em_esperado` é **obrigatório** aqui (diferente do `PUT`): aprovar é declarar "conferi
  ESTA versão", então uma ficha que mudou entre a leitura e o clique devolve `412` — é o caso em
  que o 412 deixa de ser conveniência e vira requisito.
- `400` para nome em branco; `409` se a ficha já estiver aprovada (reabra antes de aprovar de novo).

### `POST /fichas/{ficha_id}/reabrir` — `{ tenant_id, reaberta_por, observacao? }`
Devolve a ficha para edição (`EM_REVISAO`), zerando a aprovação vigente mas **preservando
`aprovacao.historico`** — é o que torna a trilha auditável. `409` se a ficha não estiver aprovada.
Sem `atualizado_em_esperado`: reabrir não declara nada sobre o conteúdo.

**Congelamento leve:** `PUT /fichas/{id}` numa ficha aprovada devolve `409`. O `PUT` também ignora
`aprovacao` vinda do corpo (escrita só por estas duas rotas), senão um cliente apagaria a trilha
de auditoria num salvamento comum. Gerar `.docx`/PDF/desenho numa ficha aprovada continua
permitido e **não rebaixa mais o status** — antes da Fase 14 isso desfazia a aprovação em silêncio.

### `DELETE /fichas/{ficha_id}?tenant_id=` — headers `X-Admin-Token`
Exige token de admin desde a Fase 14, Bloco S, Task 2 -- antes, qualquer um que soubesse o
`tenant_id` (uma string pública) apagava qualquer ficha sem autenticação nenhuma. O frontend
(`/fichas`) pede a senha administrativa na hora, via `SenhaAdminDialog`, se ainda não houver uma
sessão de admin ativa nesta aba.

### `GET /fichas/{ficha_id}/docx?tenant_id=`
Renderiza (`docxtpl`) e devolve o `.docx` para download; marca `status = DOCUMENTO_GERADO` e grava
`documentos.docx`/`documentos.gerado_em`. Sempre gerado na hora a partir dos dados atuais — nunca
serve um arquivo desatualizado de uma geração anterior.

### `GET /fichas/{ficha_id}/preview?tenant_id=`
PDF (`Content-Disposition: inline`) para exibir na tela sem marcar a ficha como emitida — rota
separada do download porque a diferença é de intenção (conferir vs. emitir), não de formato.

### `GET /fichas/{ficha_id}/pdf?tenant_id=`
PDF para download (`attachment`), convertido pelo LibreOffice a partir do mesmo `.docx` que
`GET .../docx` geraria — garante que os dois arquivos sejam visualmente idênticos. `501` se o
LibreOffice não estiver instalado neste ambiente (`LIBREOFFICE_PATH`); `500` em falha de conversão.

### `POST /fichas/{ficha_id}/desenho` — `{ tenant_id, instrucao_adicional? }`
Gera uma nova versão do desenho técnico (chamada real de API: moderação de texto + `gpt-image-1`),
protegida por `limite_imagens_dia` (mesma cota do Gerador de Croqui do chat). `instrucao_adicional`
é o ajuste da regeneração ("a manga é 3/4, não curta") — acumulado com as instruções de versões
anteriores, porque `gpt-image-1` não tem seed/determinismo e cada geração produz uma peça nova, não
uma correção pontual. `422` se o prompt for reprovado na moderação, `429` se a cota diária estourar.

### `POST /fichas/{ficha_id}/desenho/{versao}/aprovar` — `{ tenant_id }`
Marca uma versão como aprovada (rebaixando qualquer outra que estivesse). Sem chamada de API. Só a
versão aprovada entra no documento final — nenhuma é aprovada automaticamente.

### `GET /fichas/{ficha_id}/desenho/{versao}?tenant_id=`
PNG de uma versão já gerada (só leitura).

### `POST /fichas/{ficha_id}/desenho/importar-croqui` — `{ tenant_id, croqui_id }` (Fase 14, Bloco G, Task 17)
Reaproveita um croqui já salvo na galeria (`/croquis`) como uma nova versão do desenho técnico
desta ficha -- **sem** moderação, **sem** checagem de `limite_imagens_dia`, **sem** chamar
gpt-image-1: a imagem já foi moderada e cobrada quando foi gerada originalmente no chat, então
repetir qualquer uma dessas checagens cobraria/bloquearia a mesma imagem duas vezes. `400` para
`croqui_id` malformado, `404` se o croqui não existir. Marca `status = DESENHO_GERADO`, mesma
convenção de `POST /fichas/{id}/desenho`.

## Galeria de croquis (`/croquis`, Fase 14, Bloco G)

Persistência do croqui gerado no chat -- antes só existia como data URI base64 dentro do histórico
da conversa (perdido se a conversa fosse excluída). `POST /chat/croqui/confirmar` (existente) passa
a salvar em disco e devolver `croqui_id`; estas rotas só leem/listam/removem o que já foi salvo (o
único `POST` que consome um croqui salvo é `.../desenho/importar-croqui`, acima, que vive sob
`/fichas` por natureza, não sob `/croquis`).

### `GET /croquis?tenant_id=`
Lista a galeria (id, estilo, resumo, `criado_em`), mais recente primeiro -- mesmo padrão de
`GET /fichas`.

### `GET /croquis/{croqui_id}/imagem?tenant_id=`
PNG do croqui. Isenta do gate de acesso (Bloco S, Task 1) pelo mesmo motivo de
`GET /fichas/{id}/desenho/{versao}`: é consumida por `<img src>`, que não carrega header
customizado. `400` para `croqui_id` malformado, `404` se não encontrado.

### `DELETE /croquis/{croqui_id}?tenant_id=` — headers `X-Admin-Token`
Mesma exigência de `DELETE /fichas/{ficha_id}` (Bloco S, Task 2) -- excluir uma imagem já gerada é
uma ação administrativa, não uma ação de qualquer um que saiba o `tenant_id`.

## Logo da empresa (`/branding/logo`, Fase 11)

Cadastrado uma vez por tenant e reaproveitado em toda ficha gerada (`InlineImage`, redimensionado
proporcionalmente, nunca deformado). Mesma natureza de `PUT /config/tenant`: upload e remoção
exigem `X-Admin-Token`; leitura é aberta (a tela de configuração precisa exibir a prévia sem login).

### `POST /branding/logo?tenant_id=` — multipart (`arquivo`), headers `X-Admin-Token`
Aceita PNG/JPG/JPEG (SVG é recusado — o Word não o embute por este caminho); normalizado para PNG,
preservando transparência. `400` para arquivo inválido, formato não suportado ou maior que 5MB.

### `GET /branding/logo?tenant_id=`
Imagem PNG cadastrada. `404` se não houver logo.

### `GET /branding/logo/info?tenant_id=`
Metadados (`{ cadastrado: bool, metadados: { nome_original, formato_origem, largura_px, altura_px } | null }`)
sem trafegar a imagem — usado para decidir se vale a pena buscar `GET /branding/logo`.

### `DELETE /branding/logo?tenant_id=` — headers `X-Admin-Token`

## Debug/Observabilidade (uso interno)

### `GET /debug/rag?tenant_id=` — headers `X-Admin-Token`
- Último relatório de debug do pipeline RAG do `tenant_id` informado -- devolve `{}` se esse
  tenant ainda não fez nenhuma busca neste processo. Exige token de admin **do mesmo tenant**
  (Fase 13, Task 16): antes, a rota não exigia autenticação nenhuma e devolvia a pergunta e o
  texto integral dos chunks da última busca de QUALQUER tenant, ignorando o parâmetro recebido.

---

## Ferramentas do agente (referência rápida)

Schemas completos e handlers vivem em `agente_ferramentas.py` (fonte única de verdade — nunca
duplicados em `tenant_config.py`, que só referencia os nomes). Nenhuma recebe `tenant_id` ou
credenciais do modelo; esses valores vêm sempre do `ContextoExecucao` montado pelo backend.

| Ferramenta | Exige confirmação? | O que faz |
|---|---|---|
| `gerar_imagem_croqui` | Sim | Gera imagem via gpt-image-1 (OpenAI). |
| `gerar_ficha_tecnica` | Sim | **Não gera imagem.** Atalho para a área `/fichas` (Fase 12): cria uma ficha real a partir da mensagem do usuário (mesmo pipeline de `POST /fichas`) e devolve `ficha_id`/`redirecionar_para` para o frontend levar o usuário até lá. |
| `buscar_documentos_internos` | Não | Busca semântica no RAG do tenant (mesmo pipeline do modo "Base de Conhecimento"). |
| `listar_documentos_disponiveis` | Não | Lista nomes de documentos indexados, sem gerar embeddings. |
| `consultar_resumo_planilha` | Não | Resumo estatístico da planilha enviada na conversa atual. |
| `consultar_unidades_senai` | Não | Endereço/telefone/e-mail das unidades do SENAI Goiás (dado estático). |

`web_search` (nativo da OpenAI, não é uma ferramenta do registry) é habilitado por modo via
`usar_web_search: True` em `tenant_config.py` — hoje: Tendências, Engenharia Têxtil, Assistente Geral.

`buscar_documentos_internos`/`listar_documentos_disponiveis` são declaradas (`"tools"` em
`tenant_config.py`) em: Consultor de Estilo, Professor Técnico, Engenharia Têxtil, Tendências e
Assistente Geral (Fase 13, Task 17) — "Análise de Dados" e "Base de Conhecimento" têm pipeline
próprio que não passa por `tools`; "Gerador de Croqui" fica de fora por design (fluxo de
confirmação específico às duas tools de geração).

**Limitação conhecida:** `consultar_resumo_planilha` e `consultar_unidades_senai` continuam sem
nenhum modo declarando-as em `"tools"` — registradas no registry, com schema/handler/testes
próprios, mas mortas em runtime pelo mesmo motivo que motivou a Task 17 para as ferramentas de
RAG. Não fazia parte do escopo original desta task (que citava só `buscar_documentos_internos`)
religá-las também; decisão de produto pendente sobre em quais modos fariam sentido.
