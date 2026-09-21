// Tradução de erro para linguagem humana (Fase 14, Bloco U, Task 4).
//
// Antes, todo `catch` do frontend fazia `e instanceof ApiError ? e.message : padrao` -- e como
// `e.message` é o `detail` cru que o FastAPI devolve, mensagens de erro interno (nome de variável
// de ambiente, caminho de executável do LibreOffice, stdout/stderr de um subprocesso, "chunk",
// "tenant") apareciam direto no toast, na tela de uma costureira. `mensagemAmigavel()` centraliza
// essa tradução: o detalhe técnico completo sempre vai para o console (para quem for depurar),
// nunca para a tela.
import { ApiError } from "@/lib/api";

// Comparados por substring, contra o texto técnico REAL que api/main.py hoje produz -- não é uma
// lista de códigos de erro estruturados (o backend não tem isso ainda), então isto é uma tradução
// best-effort: qualquer mensagem nova e desconhecida cai no fallback de `mensagemPadrao` do
// chamador, nunca aparece crua.
const MENSAGENS_CONHECIDAS: { contem: string; amigavel: string }[] = [
  { contem: "OPENAI_API_KEY", amigavel: "O assistente está temporariamente indisponível. Avise um administrador." },
  { contem: "LibreOffice", amigavel: "Não foi possível gerar o PDF agora. Tente novamente em instantes ou avise um administrador." },
  { contem: "fpdf2", amigavel: "Não foi possível gerar o arquivo agora. Tente novamente em instantes." },
  { contem: "Nenhum chunk pôde ser gerado", amigavel: "Não foi possível ler o conteúdo desse arquivo. Verifique se ele não está vazio ou corrompido." },
  { contem: "não contém texto legível", amigavel: "Não foi possível ler o conteúdo desse arquivo. Verifique se ele não está vazio ou corrompido." },
  { contem: "conversation_id", amigavel: "Não foi possível continuar esta conversa. Recarregue a página e tente novamente." },
  { contem: "Modo '", amigavel: "Modo de conversa inválido. Recarregue a página." },
  { contem: "Tenant '", amigavel: "Não foi possível identificar esta organização. Recarregue a página ou avise um administrador." },
  { contem: "Token de admin", amigavel: "Sessão de administrador expirada. Informe a senha novamente." },
  { contem: "Acesso não autorizado", amigavel: "Sessão expirada. Informe a senha de acesso novamente." },
];

function traduzirDetalhe(mensagem: string): string | null {
  const encontrada = MENSAGENS_CONHECIDAS.find((m) => mensagem.includes(m.contem));
  return encontrada ? encontrada.amigavel : null;
}

/** Mensagem segura para mostrar na tela (toast, texto inline) a partir de um erro capturado.
 * `mensagemPadrao` é o que aparece quando a mensagem do backend não é reconhecida nem parece
 * segura de exibir como está -- sempre escreva um `mensagemPadrao` específico da ação que falhou
 * ("Falha ao enviar a mensagem."), nunca um genérico "Ocorreu um erro". */
export function mensagemAmigavel(e: unknown, mensagemPadrao: string): string {
  if (e instanceof ApiError) {
    console.error(`[API ${e.status}] ${e.message}`);
    const traduzida = traduzirDetalhe(e.message);
    if (traduzida) return traduzida;
    // Mensagens curtas de validação (400/404/409/412/413/422/429) que o backend já escreve
    // pensando no usuário final ("Limite diário atingido...", "Ficha não encontrada.") podem
    // passar direto -- qualquer coisa mais longa ou de erro interno (5xx) tem mais chance de
    // carregar detalhe técnico (stack, stdout/stderr) e cai no mensagemPadrao.
    if (e.status < 500 && e.message.length < 200) return e.message;
    return mensagemPadrao;
  }
  console.error("Erro de rede ou desconhecido:", e);
  return "Não foi possível se conectar. Verifique sua internet e tente novamente.";
}
