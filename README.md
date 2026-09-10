# SENAI LabFashion IA

Assistente de IA para a indústria da moda, multi-tenant, com 7 modos especializados (consultoria
de estilo, ensino técnico, geração de croquis/fichas técnicas, tendências, análise de dados,
base de conhecimento documental via RAG, e um assistente generalista sem restrição de escopo).

Arquitetura: **backend FastAPI** (Python) + **frontend Next.js** (React/TypeScript), separados --
não é mais a aplicação Streamlit original (código preservado na tag git `pre-remocao-streamlit`,
caso precise consultar).

---

## Arquitetura

- **Backend:** FastAPI (`api/main.py`), expõe a API REST consumida pelo frontend.
- **Frontend:** Next.js 16 / React, em `frontend/`.
- **LLM (texto):** [OpenAI](https://platform.openai.com/) (`gpt-4o` por padrão) -- chat, moderação,
  tool-calling (croqui/tendências) e síntese do RAG.
- **Geração de imagem:** OpenAI `gpt-image-1` -- croquis e desenhos técnicos de moda.
- **Busca web:** [Tavily](https://tavily.com/) -- busca real usada pelo modo Tendências.
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
| Tendências | Análise de tendências com busca real na web (Tavily), cita fontes. |
| Análise de Dados | Upload de planilha (CSV/XLSX/XLS), perguntas sobre os números -- só o resumo estatístico vai pro LLM, nunca o dado bruto. |
| Base de Conhecimento | Pergunta sobre documentos indexados pelo tenant (RAG). |
| Assistente Geral | Sem restrição de escopo a moda -- qualquer assunto. |

---

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
| `SENAI_LABFASHION_OPENAI_API_KEY` | Chat (GPT-4o), moderação, geração de imagem (gpt-image-1). |
| `SENAI_LABFASHION_ADMIN_PASSWORD` | Senha do painel administrativo (`/admin`). |
| `SENAI_LABFASHION_TAVILY_API_KEY` | Busca web do modo Tendências. |

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
python -m unittest discover -s tests   # suíte completa do backend (RAG, tool-calling, etc.)
cd frontend && npm run build           # valida o build de produção do frontend
```

Um workflow de CI (`.github/workflows/ci.yml`) roda os dois automaticamente em todo push/PR.

## Logs e diagnóstico

- Logs vão tanto para stdout (essencial em containers) quanto para `logs/app.log`
  (`RotatingFileHandler`, 5MB por arquivo, até 5 arquivos históricos).
- Nível configurável via `LOG_LEVEL` (default `INFO`).
- **Privacidade:** nenhuma chave de API, senha administrativa ou conteúdo bruto de prompt do
  usuário é gravado em log.
