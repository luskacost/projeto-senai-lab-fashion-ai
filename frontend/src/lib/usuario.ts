// Identificação simples de usuário por navegador (sem autenticação real),
// mesma filosofia de conversas_manager.py: identificação por conveniência/UX,
// não uma autenticação robusta. Um UUID estável é gerado e persistido em
// localStorage na primeira visita.

const CHAVE_USUARIO_ID = "labfashion_usuario_id";
const CHAVE_PERFIL_USUARIO = "labfashion_perfil_usuario";

export function obterUsuarioId(): string {
  if (typeof window === "undefined") return "";
  let id = window.localStorage.getItem(CHAVE_USUARIO_ID);
  if (!id) {
    id = crypto.randomUUID();
    window.localStorage.setItem(CHAVE_USUARIO_ID, id);
  }
  return id;
}

// Perfil de usuário (papel dentro da empresa de moda -- ver lib/perfis.ts). Ao contrário
// de obterUsuarioId(), aqui não existe valor gerado por padrão: começa como "nenhum
// perfil escolhido" (null) até a pessoa escolher um pelo SeletorPerfil, e pode ser limpo
// a qualquer momento -- é opcional, nunca bloqueia o uso do app.
export function obterPerfilAtivo(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(CHAVE_PERFIL_USUARIO);
}

export function definirPerfilAtivo(perfil: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CHAVE_PERFIL_USUARIO, perfil);
}

export function limparPerfilAtivo(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CHAVE_PERFIL_USUARIO);
}
