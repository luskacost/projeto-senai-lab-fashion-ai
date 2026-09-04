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

export interface ChatResponse {
  resposta: string;
  fontes_consultadas: string[];
  trechos_consultados: ChunkConsultado[];
}

export async function enviarMensagemChat(params: {
  tenantId: string;
  mensagem: string;
  modo: string;
  conversationId?: string | null;
  perfilUsuario?: string | null;
}): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      tenant_id: params.tenantId,
      mensagem: params.mensagem,
      modo: params.modo,
      conversation_id: params.conversationId ?? null,
      perfil_usuario: params.perfilUsuario ?? null,
    }),
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

export interface MensagemConversa {
  role: "user" | "assistant";
  content: string;
  mode?: string;
  tenant_id?: string;
  fontes_consultadas?: string[];
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

export async function adminLogin(tenantId: string, senha: string): Promise<boolean> {
  const resultado = await request<{ autorizado: boolean }>("/admin/login", {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId, senha }),
  });
  return resultado.autorizado;
}

export async function listarDocumentos(tenantId: string): Promise<string[]> {
  return request<string[]>(`/documentos?tenant_id=${encodeURIComponent(tenantId)}`);
}

export interface UploadDocumentoResponse {
  nome_arquivo: string;
  chunks_indexados: number;
}

export async function uploadDocumento(tenantId: string, arquivo: File): Promise<UploadDocumentoResponse> {
  const formData = new FormData();
  formData.append("arquivo", arquivo);

  const res = await fetch(`${API_URL}/documentos/upload?tenant_id=${encodeURIComponent(tenantId)}`, {
    method: "POST",
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

export async function deletarDocumento(tenantId: string, nomeArquivo: string): Promise<void> {
  await request<{ status: string }>(
    `/documentos/${encodeURIComponent(nomeArquivo)}?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "DELETE" }
  );
}
