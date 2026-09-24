// Login de acesso ao app (Fase 14, Bloco S; virou login por tenant/pessoa na Fase 16, Bloco L) --
// não é uma conta de usuário completa, é "qual consultoria/tenant está usando o app" mais uma
// senha compartilhada só entre quem precisa saber. Token opaco emitido por POST /acesso/login e
// validado no backend em toda rota (ver api/main.py:verificar_acesso), persistido em localStorage
// (não sessionStorage) porque é usado no dia a dia, não numa sessão administrativa pontual --
// mesma filosofia de obterUsuarioId() em lib/usuario.ts.
//
// Fase 16: o backend agora pode rodar em modo "login por tenant" (quando pelo menos um tenant tem
// LOGIN_SENHA configurada) -- nesse modo, o login devolve também qual tenant_id o token
// pertence, e o restante do app (páginas que hoje leem NEXT_PUBLIC_TENANT_ID) precisa usar ESSE
// valor em vez do default de build. Sem login por tenant (modo legado, dev local),
// `obterTenantIdAtivo()` simplesmente não tem nada guardado e quem chama cai no próprio fallback.

const CHAVE_TOKEN_ACESSO = "labfashion_access_token";
const CHAVE_TENANT_ID_ATIVO = "labfashion_tenant_id_ativo";

export function obterTokenAcesso(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(CHAVE_TOKEN_ACESSO);
}

export function definirTokenAcesso(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CHAVE_TOKEN_ACESSO, token);
}

export function limparTokenAcesso(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CHAVE_TOKEN_ACESSO);
}

// `null` = login legado (senha única, sem tenant nenhum atrelado ao token) -- só existe um valor
// aqui quando o backend está em modo "login por tenant" e devolveu um `tenant_id` no login.
export function obterTenantIdAtivo(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(CHAVE_TENANT_ID_ATIVO);
}

export function definirTenantIdAtivo(tenantId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CHAVE_TENANT_ID_ATIVO, tenantId);
}

export function limparTenantIdAtivo(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CHAVE_TENANT_ID_ATIVO);
}

// Callback único registrado pelo componente de portão (PortaoDeAcesso.tsx) na montagem da
// aplicação. Centraliza a reação a "o token de acesso não vale mais" num só lugar (api.ts chama
// isto sempre que o backend devolve o header X-Auth-Gate: acesso) -- nenhuma página individual
// precisa saber verificar isso sozinha.
let aoPerderAcesso: (() => void) | null = null;

export function registrarAoPerderAcesso(callback: () => void): void {
  aoPerderAcesso = callback;
}

export function notificarPerdaDeAcesso(): void {
  limparTokenAcesso();
  limparTenantIdAtivo();
  aoPerderAcesso?.();
}
