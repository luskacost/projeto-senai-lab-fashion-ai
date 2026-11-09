# Frontend — SENAI LabFashion IA

Interface Next.js (React/TypeScript) do assistente. A documentação completa do projeto (arquitetura,
variáveis de ambiente, deploy) está no [README da raiz](../README.md).

## Rodar em desenvolvimento

Com o backend rodando em `http://localhost:8000` (ver README da raiz):

```bash
npm install
npm run dev
```

Acesse [http://localhost:3000](http://localhost:3000).

`NEXT_PUBLIC_API_URL` e `NEXT_PUBLIC_TENANT_ID` são lidos em tempo de build — defina-os em
`frontend/.env.local` se precisar de valores diferentes dos padrões de desenvolvimento.
