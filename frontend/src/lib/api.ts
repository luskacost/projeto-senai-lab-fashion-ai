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
