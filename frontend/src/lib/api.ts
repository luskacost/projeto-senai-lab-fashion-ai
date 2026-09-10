// Cliente da API do SenaiLabFashionAssistant (api/main.py).
// Tipos e chamadas espelham o contrato em API_CONTRATO.md.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // corpo nao era JSON valido, mantem statusText
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

export interface ChunkConsultado {
  fonte: string;
  rotulo_unidade?: string;
  pagina?: number;
  texto: string;
  score?: number;
}

// Passada de volta inalterada pelo front-end em POST /chat/croqui/confirmar -- o conteúdo
// é opaco para o cliente, só precisa ser guardado em memória entre as duas chamadas.
export type PendenteConfirmacao = Record<string, unknown> & { resumo_confirmacao?: string };

export interface ChatResponse {
  resposta: string | null;
  fontes_consultadas: string[];
  trechos_consultados: ChunkConsultado[];
  imagem_url?: string | null;
  pendente_confirmacao?: PendenteConfirmacao | null;
}

export async function enviarMensagemChat(params: {
  tenantId: string;
  mensagem: string;
  modo: string;
  conversationId?: string | null;
  perfilUsuario?: string | null;
  historico?: { role: string; content: string }[];
  estiloCroqui?: string;
}): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      tenant_id: params.tenantId,
      mensagem: params.mensagem,
      modo: params.modo,
      conversation_id: params.conversationId ?? null,
      perfil_usuario: params.perfilUsuario ?? null,
      historico: params.historico ?? null,
      estilo_croqui: params.estiloCroqui ?? null,
    }),
  });
}

export interface ConfirmarCroquiResponse {
  resposta: string;
  imagem_url: string | null;
}

export async function confirmarCroqui(
  tenantId: string,
  confirmado: boolean,
  pendente: PendenteConfirmacao
): Promise<ConfirmarCroquiResponse> {
  return request<ConfirmarCroquiResponse>("/chat/croqui/confirmar", {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId, confirmado, pendente }),
  });
}

export interface TenantConfig {
  nome: string;
  cor_primaria: string;
  cor_secundaria: string;
  mensagem_boas_vindas?: string;
  [key: string]: unknown;
}

export async function obterConfigTenant(tenantId: string): Promise<TenantConfig> {
  return request<TenantConfig>(`/config/tenant?tenant_id=${encodeURIComponent(tenantId)}`);
}

export interface AparenciaTenant {
  nome: string;
  cor_primaria: string;
  cor_secundaria: string;
  logo_url: string;
  tema: "claro" | "escuro";
  fonte: string;
  favicon_url: string;
  mensagem_boas_vindas: string;
}

export async function atualizarConfigTenant(tenantId: string, dadosCustom: AparenciaTenant, tokenAdmin: string): Promise<void> {
  await request<{ status: string }>("/config/tenant", {
    method: "PUT",
    headers: { "X-Admin-Token": tokenAdmin },
    body: JSON.stringify({ tenant_id: tenantId, dados_custom: dadosCustom }),
  });
}

export interface GraficoBarrasDados {
  titulo: string;
  itens: { rotulo: string; valor: number }[];
}

export interface ColunasAnalisadas {
  agrupamento: string[];
  metricas: string[];
}

export interface ArquivoAnexado {
  nome: string;
  linhas: number;
  colunas: number;
  grafico?: GraficoBarrasDados | null;
  colunasAnalisadas?: ColunasAnalisadas | null;
}

export interface MensagemConversa {
  role: "user" | "assistant";
  content: string;
  mode?: string;
  tenant_id?: string;
  fontes_consultadas?: string[];
  trechos_consultados?: ChunkConsultado[];
  imagem_url?: string | null;
  arquivo_anexado?: ArquivoAnexado | null;
}

export interface Conversa {
  id: string;
  titulo: string;
  mensagens: MensagemConversa[];
  criado_em: string;
  atualizado_em: string;
}

export async function listarConversas(tenantId: string, usuarioId: string): Promise<Conversa[]> {
  return request<Conversa[]>(
    `/conversas?tenant_id=${encodeURIComponent(tenantId)}&usuario_id=${encodeURIComponent(usuarioId)}`
  );
}

export async function criarConversa(tenantId: string, usuarioId: string): Promise<Conversa> {
  return request<Conversa>("/conversas", {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId, usuario_id: usuarioId }),
  });
}

export async function atualizarConversa(
  tenantId: string,
  usuarioId: string,
  conversaId: string,
  atualizacoes: { novoTitulo?: string; mensagens?: MensagemConversa[] }
): Promise<Conversa> {
  return request<Conversa>(`/conversas/${encodeURIComponent(conversaId)}`, {
    method: "PATCH",
    body: JSON.stringify({
      tenant_id: tenantId,
      usuario_id: usuarioId,
      novo_titulo: atualizacoes.novoTitulo ?? null,
      mensagens: atualizacoes.mensagens ?? null,
    }),
  });
}

export async function deletarConversa(tenantId: string, usuarioId: string, conversaId: string): Promise<void> {
  await request<{ status: string }>(
    `/conversas/${encodeURIComponent(conversaId)}?tenant_id=${encodeURIComponent(tenantId)}&usuario_id=${encodeURIComponent(usuarioId)}`,
    { method: "DELETE" }
  );
}

// POST /admin/login agora emite um token de sessão (Fase 9, Bloco B) -- o front-end guarda esse
// token (não mais um simples "1") e precisa enviá-lo de volta no header X-Admin-Token em toda
// rota administrativa de verdade (upload/remoção de documentos, config do tenant), que agora
// checa esse token no backend em vez de confiar só na tela de login escondendo o botão.
export async function adminLogin(tenantId: string, senha: string): Promise<string | null> {
  const resultado = await request<{ autorizado: boolean; token: string | null }>("/admin/login", {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId, senha }),
  });
  return resultado.autorizado ? resultado.token : null;
}

export async function listarDocumentos(tenantId: string): Promise<string[]> {
  return request<string[]>(`/documentos?tenant_id=${encodeURIComponent(tenantId)}`);
}

export interface UploadDocumentoResponse {
  nome_arquivo: string;
  chunks_indexados: number;
}

export async function uploadDocumento(tenantId: string, arquivo: File, tokenAdmin: string): Promise<UploadDocumentoResponse> {
  const formData = new FormData();
  formData.append("arquivo", arquivo);

  const res = await fetch(`${API_URL}/documentos/upload?tenant_id=${encodeURIComponent(tenantId)}`, {
    method: "POST",
    headers: { "X-Admin-Token": tokenAdmin },
    body: formData,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // corpo nao era JSON valido, mantem statusText
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<UploadDocumentoResponse>;
}

export interface AgregacaoResumo {
  top_10: Record<string, number>;
  bottom_10: Record<string, number>;
  total_geral: number;
  media_por_grupo: number;
}

// resumo["agregacoes"][categoria][metrica] -- ver analise_dados.py:gerar_resumo_estatistico.
export type AgregacoesResumo = Record<string, Record<string, AgregacaoResumo>>;

export interface ResumoEstatistico {
  agregacoes?: AgregacoesResumo;
  colunas_selecionadas_para_analise?: ColunasAnalisadas;
  [key: string]: unknown;
}

export interface UploadPlanilhaResponse {
  nome_arquivo: string;
  linhas: number;
  colunas: string[];
  resumo_estatistico?: ResumoEstatistico;
}

// Faz upload de uma planilha (CSV/XLSX/XLS) para o modo "Análise de Dados". O resumo
// estatístico gerado fica persistido no backend por conversation_id -- as próximas
// mensagens de chat nessa conversa (modo "Análise de Dados") o reaproveitam automaticamente.
export async function uploadPlanilha(
  tenantId: string,
  conversationId: string,
  arquivo: File
): Promise<UploadPlanilhaResponse> {
  const formData = new FormData();
  formData.append("arquivo", arquivo);

  const res = await fetch(
    `${API_URL}/planilha/upload?tenant_id=${encodeURIComponent(tenantId)}&conversation_id=${encodeURIComponent(conversationId)}`,
    { method: "POST", body: formData }
  );

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // corpo nao era JSON valido, mantem statusText
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<UploadPlanilhaResponse>;
}

export async function deletarDocumento(tenantId: string, nomeArquivo: string, tokenAdmin: string): Promise<void> {
  await request<{ status: string }>(
    `/documentos/${encodeURIComponent(nomeArquivo)}?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "DELETE", headers: { "X-Admin-Token": tokenAdmin } }
  );
}

// Baixa a exportação de uma conversa (TXT ou PDF) e dispara o download no navegador,
// já que a resposta é um arquivo binário/texto, não JSON.
export async function baixarExportacaoConversa(
  tenantId: string,
  usuarioId: string,
  conversaId: string,
  formato: "txt" | "pdf"
): Promise<void> {
  const url =
    `${API_URL}/conversas/${encodeURIComponent(conversaId)}/export` +
    `?tenant_id=${encodeURIComponent(tenantId)}&usuario_id=${encodeURIComponent(usuarioId)}&formato=${formato}`;

  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // corpo nao era JSON valido, mantem statusText
    }
    throw new ApiError(res.status, detail);
  }

  const blob = await res.blob();
  const nomeArquivo = `conversa_${tenantId}.${formato}`;
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = nomeArquivo;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}
