# SENAI Lab Fashion Assistant 👗👕

Aplicação Streamlit multi-tenant para assistência e recomendação de moda, com suporte a customização dinâmica de marca por tenant e integração com Groq LLM.

---

## 🐋 Como rodar com Docker

Para executar a aplicação em qualquer máquina sem a necessidade de instalar o Python ou gerenciar dependências manualmente:

1. **Configurar as variáveis de ambiente:**
   Copie o arquivo `.env.example` para `.env` e preencha as variáveis com as chaves reais (ex: `GROQ_API_KEY`):
   ```bash
   cp .env.example .env
   ```

2. **Iniciar o container via Docker Compose:**
   Execute o comando abaixo para construir a imagem e subir o serviço:
   ```bash
   docker compose up --build
   ```

3. **Acessar a aplicação:**
   Abra o navegador em:
   - **Tenant Padrão / Padrão:** [http://localhost:8501](http://localhost:8501)
   - **Tenant Específico:** [http://localhost:8501/?tenant=nome_do_tenant](http://localhost:8501/?tenant=nome_do_tenant)

---

## 📊 Logs e Diagnóstico

O sistema utiliza logging estruturado para capturar eventos de negócio e exceções técnicas sem expor detalhes internos na interface do usuário:

- **Localização dos arquivos de log:** `logs/app.log`
- **Como visualizar em tempo real:**
  ```bash
  tail -f logs/app.log
  ```
- **Rotação automática:** O arquivo `app.log` é gerenciado via `RotatingFileHandler` (máximo de 5 MB por arquivo, mantendo até 5 arquivos históricos `app.log.1`, `app.log.2`, etc.).
- **Privacidade:** Nenhuma chave de API, senha administrativa ou conteúdo de prompt do usuário é armazenado nos logs.

---

---

## 📚 RAG / Base de Conhecimento

A aplicação conta com o modo **Base de Conhecimento** alimentado por RAG (*Retrieval-Augmented Generation*), permitindo que cada empresa faça upload de manuais, apostilas e fichas técnicas em PDF para que o assistente responda dúvidas citando as fontes exatas.

### Arquitetura e Stack
- **Banco Vetorial:** [ChromaDB](https://www.trychroma.com/) embutido e autogerenciado (*self-hosted*).
- **Embeddings Locais:** [Sentence-Transformers](https://www.sbert.net/) com o modelo multilíngue `paraphrase-multilingual-MiniLM-L12-v2` (execução 100% local em CPU, sem custo de API para vetorização).
- **Geração de Resposta:** [Groq API](https://groq.com/) com o modelo LLM do projeto, combinando o prompt do sistema com os trechos mais relevantes recuperados da busca semântica.
- **Extração de Texto:** `pypdf` para leitura e particionamento dos PDFs em blocos (*chunks*) com sobreposição de contexto.

### Isolamento Multi-tenant e Persistência
- Os índices vetoriais de cada empresa são gravados no diretório `tenant_data/chroma/{tenant_id}/`.
- O isolamento físico garante que uma busca realizada por um tenant **nunca** tenha acesso ou retorne documentos de outros tenants.
- No Docker, o diretório `tenant_data/` é montado como volume persistente (`./tenant_data:/app/tenant_data`), garantindo que todos os documentos indexados persistam entre reinicializações do container.

### Como o Administrador Adiciona Documentos
1. Acesse o aplicativo e abra a aba **⚙️ Configurações**.
2. Digite a senha de administrador do tenant para autenticar.
3. Na seção **📚 Base de Conhecimento**, envie um ou mais arquivos PDF no campo de upload.
4. Clique no botão **📥 Indexar documentos**. A barra de progresso exibirá a extração e a inserção vetorial no ChromaDB.
5. Os materiais indexados ficarão listados na tela com a opção de remoção individual (**🗑️ Remover**) e imediatamente disponíveis para todos os usuários do tenant no modo **Base de Conhecimento**.



