// Sessão de admin (Fase 9, Bloco B) -- token emitido por POST /admin/login, exigido em X-Admin-Token
// nas rotas administrativas. Guardado em sessionStorage (não localStorage): sessão pontual de
// quem está gerenciando conteúdo agora, não uma identidade de longo prazo como o token de acesso
// (lib/acesso.ts). Extraído de admin/page.tsx para ser reaproveitado por qualquer tela que
// precise confirmar uma ação administrativa (ex: apagar uma ficha em /fichas, Fase 14).

const CHAVE_SESSAO_ADMIN = "labfashion_admin_token";

export function obterTokenAdmin(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(CHAVE_SESSAO_ADMIN);
}

export function definirTokenAdmin(token: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(CHAVE_SESSAO_ADMIN, token);
}

export function limparTokenAdmin(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(CHAVE_SESSAO_ADMIN);
}
