// Identificação simples de usuário por navegador (sem autenticação real),
// mesma filosofia de conversas_manager.py: identificação por conveniência/UX,
// não uma autenticação robusta. Um UUID estável é gerado e persistido em
// localStorage na primeira visita.

const CHAVE_USUARIO_ID = "labfashion_usuario_id";

export function obterUsuarioId(): string {
  if (typeof window === "undefined") return "";
  let id = window.localStorage.getItem(CHAVE_USUARIO_ID);
  if (!id) {
    id = crypto.randomUUID();
    window.localStorage.setItem(CHAVE_USUARIO_ID, id);
  }
  return id;
}
