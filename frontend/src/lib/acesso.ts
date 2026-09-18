// Senha única de acesso ao app inteiro (Fase 14, Bloco S) -- não é login por pessoa, é uma porta
// fechada para quem não sabe a senha compartilhada da organização. Token opaco emitido por
// POST /acesso/login e validado no backend em toda rota (ver api/main.py:verificar_acesso),
// persistido em localStorage (não sessionStorage) porque é usado no dia a dia, não numa sessão
// administrativa pontual -- mesma filosofia de obterUsuarioId() em lib/usuario.ts.

const CHAVE_TOKEN_ACESSO = "labfashion_access_token";

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
  aoPerderAcesso?.();
}
