// Cliente da API do SenaiLabFashionAssistant (api/main.py).
// Tipos e chamadas espelham o contrato em API_CONTRATO.md.

import { notificarPerdaDeAcesso, obterTokenAcesso } from "@/lib/acesso";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Anexado em toda chamada (Fase 14, Bloco S) -- rotas isentas (ver API_CONTRATO.md) simplesmente
// ignoram o header, então é seguro mandar sempre, mesmo sem token ainda (valor null vira ausente).
function headerDeAcesso(): Record<string, string> {
  const token = obterTokenAcesso();
  return token ? { "X-Access-Token": token } : {};
}

// Único ponto que interpreta uma resposta de erro do backend -- usado tanto por request() quanto
// pelas duas chamadas de upload (FormData) que não passam por ela. Centraliza também a detecção
// do header X-Auth-Gate: acesso, que dispara a volta à tela de senha de acesso (Fase 14, Bloco S)
// sem que cada página precise verificar isso sozinha.
async function erroDaResposta(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail = body.detail ?? detail;
  } catch {
    // corpo nao era JSON valido, mantem statusText
  }
  if (res.status === 401 && res.headers.get("X-Auth-Gate") === "acesso") {
    notificarPerdaDeAcesso();
  }
  return new ApiError(res.status, detail);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...headerDeAcesso(),
      ...(options?.headers ?? {}),
    },
  });

  if (!res.ok) {
    throw await erroDaResposta(res);
  }

  return res.json() as Promise<T>;
}

export interface ChunkConsultado {
  fonte: string;
  rotulo_unidade?: string;
  pagina?: number;
  texto: string;
  score?: number;
  // Só presente quando a fonte veio de uma busca real na web (web_search nativo) -- documentos
  // internos (RAG) não têm URL real, então o campo fica ausente/null (Fase 10, Task 10).
  url?: string | null;
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
  // True quando o agente usou o web_search nativo para responder (Fase 10, Task 10) -- distingue
  // "respondendo com conhecimento do modelo" de "pesquisou na web antes de responder".
  usou_busca_web?: boolean;
  // True quando o modo usa busca web mas o limite diário já foi atingido, então esta resposta
  // saiu sem pesquisar (Fase 14, Bloco U, Task 9) -- antes essa degradação era silenciosa.
  busca_web_desligada_por_cota?: boolean;
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
  // Presente quando a imagem foi gerada com sucesso (Fase 14, Bloco G, Task 14) -- o croqui já foi
  // persistido na galeria (/croquis); null se a gravação em disco falhou (best-effort, nunca
  // derruba a resposta) ou se este pendente não gerou imagem nenhuma.
  croqui_id?: string | null;
  // Só presentes quando pendente.nome_ferramenta é "gerar_ficha_tecnica" (Fase 12) -- a ferramenta
  // não gera imagem, cria uma ficha real em /fichas e devolve o link pra lá.
  ficha_id?: string | null;
  redirecionar_para?: string | null;
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
  // Fase 14, Bloco G, Task 15: id na galeria (/croquis) do croqui gerado nesta mensagem. Quando
  // presente, o frontend busca a imagem por urlCroqui() em vez de usar `imagem_url` (que continua
  // preenchido só para não quebrar conversas antigas, persistidas antes desta task, sem
  // croqui_id -- essas continuam consumindo a data URI base64 diretamente).
  croqui_id?: string | null;
  arquivo_anexado?: ArquivoAnexado | null;
  usou_busca_web?: boolean;
  // Fase 12: presente quando esta resposta veio do atalho gerar_ficha_tecnica -- link para a
  // ficha real recém-criada em /fichas.
  ficha_link?: string | null;
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
export interface ResultadoAcessoLogin {
  autorizado: boolean;
  token: string | null;
  tenantId: string | null;
}

// tenantId é opcional -- no modo legado (dev local, nenhum tenant com LOGIN_SENHA configurada no
// backend), o login não pede tenant nenhum, só a senha única (Fase 14/15). No modo por
// tenant/pessoa (Fase 16, Bloco L), o backend exige tenant_id e devolve de volta qual tenant o
// token emitido pertence.
export async function acessoLogin(senha: string, tenantId?: string): Promise<ResultadoAcessoLogin> {
  const resultado = await request<{ autorizado: boolean; token: string | null; tenant_id?: string | null }>(
    "/acesso/login",
    { method: "POST", body: JSON.stringify({ senha, tenant_id: tenantId }) },
  );
  return {
    autorizado: resultado.autorizado,
    token: resultado.autorizado ? resultado.token : null,
    tenantId: resultado.autorizado ? (resultado.tenant_id ?? null) : null,
  };
}

// Fase 15, V6: rota já existia no backend, sem uso nenhum no frontend ainda -- este é o primeiro
// lugar que a chama de verdade (Fase 16, Bloco L).
export async function acessoLogout(): Promise<void> {
  await request<{ status: string }>("/acesso/logout", { method: "POST" });
}

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

export interface UsoCategoria {
  usado: number;
  limite: number;
  restante: number;
}

export interface UsoDiario {
  data: string;
  categorias: {
    mensagens: UsoCategoria;
    imagens: UsoCategoria;
    buscas_web: UsoCategoria;
    fichas: UsoCategoria;
  };
}

// Fase 14, Bloco U, Task 9 -- pro indicador discreto "restam N mensagens hoje", pra o limite
// diário não chegar como surpresa na hora de enviar.
export async function obterUso(tenantId: string): Promise<UsoDiario> {
  return request<UsoDiario>(`/uso?tenant_id=${encodeURIComponent(tenantId)}`);
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
    headers: { "X-Admin-Token": tokenAdmin, ...headerDeAcesso() },
    body: formData,
  });

  if (!res.ok) {
    throw await erroDaResposta(res);
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
    { method: "POST", headers: headerDeAcesso(), body: formData }
  );

  if (!res.ok) {
    throw await erroDaResposta(res);
  }

  return res.json() as Promise<UploadPlanilhaResponse>;
}

export async function deletarDocumento(tenantId: string, nomeArquivo: string, tokenAdmin: string): Promise<void> {
  await request<{ status: string }>(
    `/documentos/${encodeURIComponent(nomeArquivo)}?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "DELETE", headers: { "X-Admin-Token": tokenAdmin } }
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// FICHAS TÉCNICAS DE MODA (Fase 11)
// ─────────────────────────────────────────────────────────────────────────────
export type StatusFicha =
  | "RASCUNHO"
  | "EM_REVISAO"
  | "DESENHO_GERADO"
  | "AGUARDANDO_APROVACAO"
  | "APROVADA"
  | "DOCUMENTO_GERADO";

// Histórico leve (GET /fichas) -- espelha fichas_repo._resumo_indice, não o documento completo.
export interface FichaResumo {
  id: string;
  ref: string;
  nome: string;
  status: StatusFicha;
  criado_em: string;
  atualizado_em: string;
  // Vazio quando a ficha não está aprovada (Fase 14, Bloco AP). Vem no índice para a lista
  // mostrar quem aprovou sem precisar abrir o JSON completo de cada ficha.
  aprovada_por?: string;
}

export type OrigemCampo = "FORNECIDO" | "OBSERVADO" | "INFERIDO" | "DESCONHECIDO";

// Todo campo de valor extraído carrega de onde veio (fichas_modelo.py, backend) -- a base da
// regra de não-invenção: preço/composição/fornecedor etc. nunca aparecem como fato se a origem
// não for FORNECIDO. A tela de revisão (Task 8) usa isso para destacar campo por campo.
export interface CampoFicha<T> {
  valor: T;
  origem: OrigemCampo;
  trecho: string;
}

// Espelha fichas_modelo.py (backend) campo a campo -- os nomes de chave são os mesmos dos dois
// lados de propósito, pra tornar o mapeamento request/response óbvio de olhar.
export interface CamposIdentificacao {
  ref: CampoFicha<string>;
  nome: CampoFicha<string>;
  colecao: CampoFicha<string>;
  descricao: CampoFicha<string>;
  designer: CampoFicha<string>;
  tecnica: CampoFicha<string>;
  empresa: CampoFicha<string>;
  data: CampoFicha<string>;
}

export interface CorBeneficiamento {
  item: CampoFicha<string>;
  descricao: CampoFicha<string>;
  cor: CampoFicha<string>;
  beneficiamento: CampoFicha<string>;
  observacoes: CampoFicha<string>;
}

export interface Aviamento {
  descricao: CampoFicha<string>;
  composicao: CampoFicha<string>;
  cor: CampoFicha<string>;
  quantidade: CampoFicha<number | null>;
  fornecedor: CampoFicha<string>;
  preco: CampoFicha<number | null>;
}

export interface Tecido {
  descricao: CampoFicha<string>;
  composicao: CampoFicha<string>;
  cor: CampoFicha<string>;
  quantidade: CampoFicha<number | null>;
  largura: CampoFicha<number | null>;
  fornecedor: CampoFicha<string>;
  preco: CampoFicha<number | null>;
}

export interface CategoriaCusto {
  custo: CampoFicha<number | null>;
  observacao: CampoFicha<string>;
}

export interface Operacao {
  descricao: CampoFicha<string>;
  maquinas: CampoFicha<string>;
}

export interface ParteModelagem {
  descricao: CampoFicha<string>;
  observacoes: CampoFicha<string>;
}

// Uma linha da tabela de medidas (Fase 14, Bloco M): o ponto medido e uma célula por tamanho da
// grade. `valores` é indexado por tamanho ("38", "M") -- as colunas saem da grade, não desta
// chave, então um tamanho sem célula aqui aparece em branco, e uma célula de tamanho que saiu da
// grade não é exibida (o backend alerta sobre ela na revisão).
export interface LinhaMedida {
  ponto: CampoFicha<string>;
  valores: Record<string, CampoFicha<number | null>>;
}

export interface DadosFicha {
  ficha: CamposIdentificacao;
  cores_beneficiamentos: CorBeneficiamento[];
  grade: {
    numericos: CampoFicha<string[]>;
    comerciais: CampoFicha<string[]>;
  };
  // Única chave de "dados" que não vem da extração (fichas_modelo.CHAVES_NAO_EXTRAIDAS) -- pode
  // faltar em ficha salva antes da Fase 14, por isso opcional aqui.
  medidas?: LinhaMedida[];
  aviamentos: Aviamento[];
  tecidos: Tecido[];
  custos: {
    aviamentos: CategoriaCusto;
    tecidos: CategoriaCusto;
    costura_beneficiamento: CategoriaCusto;
    outros: CategoriaCusto;
    preco_total: CategoriaCusto;
  };
  sequencia_operacional: Operacao[];
  modelagem: {
    modelista: CampoFicha<string>;
    numero_moldes: CampoFicha<number | null>;
    partes: ParteModelagem[];
  };
}

// Status de cada versão -- nenhum desenho é aprovado automaticamente, só por ação explícita do
// usuário (aprovarDesenho). "gerado" existe no backend por completude (fichas_modelo.py) mas não
// aparece de fato neste fluxo síncrono: toda versão já nasce AGUARDANDO_APROVACAO.
export type StatusDesenho = "gerado" | "aguardando_aprovacao" | "aprovado";

export interface VersaoDesenho {
  versao: number;
  prompt_visual: string;
  instrucoes_acumuladas: string;
  status: StatusDesenho;
  criado_em: string;
}

export interface DesenhoFicha {
  solicitado: boolean;
  versoes: VersaoDesenho[];
  versao_aprovada: number | null;
}

// Parâmetros do preço sugerido (Fase 14, Bloco P, Task 19) -- FORA de "dados" de propósito
// (mesmo motivo do backend: markup não é algo que um LLM deveria extrair do texto do usuário).
// Editável como qualquer outro campo da ficha, salvo por PUT /fichas/{id} normalmente.
export interface PrecificacaoFicha {
  imposto_percentual: number;
  comissao_percentual: number;
  margem_lucro_percentual: number;
}

// Registro de aprovação (Fase 14, Bloco AP). REGISTRO NOMINAL, não assinatura digital: guarda o
// nome que a pessoa digitou, sem autenticação por trás -- a UI precisa chamá-lo assim, porque
// prometer "assinatura" seria prometer uma garantia criptográfica que este campo não tem.
// Os campos do topo são a aprovação vigente (zerados ao reabrir); `historico` só cresce.
export interface EventoAprovacao {
  acao: "aprovada" | "reaberta";
  por: string;
  em: string;
  observacao: string;
}

export interface AprovacaoFicha {
  aprovada_por: string;
  aprovada_em: string;
  observacao: string;
  historico: EventoAprovacao[];
}

export interface Ficha {
  id: string;
  status: StatusFicha;
  criado_em: string;
  atualizado_em: string;
  texto_origem: string;
  dados: DadosFicha;
  desenho: DesenhoFicha;
  precificacao: PrecificacaoFicha;
  // Pode faltar em ficha salva antes da Fase 14, por isso opcional.
  aprovacao?: AprovacaoFicha;
  documentos: { docx: string; pdf: string; gerado_em: string };
}

// Construtores de item vazio para as listas dinâmicas -- espelham fichas_modelo.py
// (aviamento_vazio, tecido_vazio, cor_beneficiamento_vazia, operacao_vazia, parte_modelagem_vazia),
// usados quando o usuário clica "Adicionar linha" no editor (Task 8), sem precisar de round-trip
// com o backend só para obter a forma de um item novo.
function campoTextoVazio(): CampoFicha<string> {
  return { valor: "", origem: "DESCONHECIDO", trecho: "" };
}

// Exportado (ao contrário de campoTextoVazio) porque a tabela de medidas precisa de um campo
// vazio de fallback: uma linha criada antes de um tamanho entrar na grade não tem célula para
// ele, e a coluna precisa renderizar em branco em vez de quebrar.
export function campoNumeroVazio(): CampoFicha<number | null> {
  return { valor: null, origem: "DESCONHECIDO", trecho: "" };
}

export function corBeneficiamentoVazia(): CorBeneficiamento {
  return {
    item: campoTextoVazio(),
    descricao: campoTextoVazio(),
    cor: campoTextoVazio(),
    beneficiamento: campoTextoVazio(),
    observacoes: campoTextoVazio(),
  };
}

export function aviamentoVazio(): Aviamento {
  return {
    descricao: campoTextoVazio(),
    composicao: campoTextoVazio(),
    cor: campoTextoVazio(),
    quantidade: campoNumeroVazio(),
    fornecedor: campoTextoVazio(),
    preco: campoNumeroVazio(),
  };
}

export function tecidoVazio(): Tecido {
  return {
    descricao: campoTextoVazio(),
    composicao: campoTextoVazio(),
    cor: campoTextoVazio(),
    quantidade: campoNumeroVazio(),
    largura: campoNumeroVazio(),
    fornecedor: campoTextoVazio(),
    preco: campoNumeroVazio(),
  };
}

export function operacaoVazia(): Operacao {
  return { descricao: campoTextoVazio(), maquinas: campoTextoVazio() };
}

export function parteModelagemVazia(): ParteModelagem {
  return { descricao: campoTextoVazio(), observacoes: campoTextoVazio() };
}

// Espelha fichas_modelo.linha_medida_vazia: uma célula por tamanho da grade atual. Recebe os
// tamanhos prontos (não os deriva) para não precisar duplicar aqui a lista de tamanhos válidos.
export function linhaMedidaVazia(tamanhos: string[]): LinhaMedida {
  return {
    ponto: campoTextoVazio(),
    valores: Object.fromEntries(tamanhos.map((t) => [t, campoNumeroVazio()])),
  };
}

// Constrói um CampoFicha marcado como editado manualmente pelo usuário -- FORNECIDO porque a
// pessoa acabou de digitar/selecionar o valor com a própria mão, sem "trecho" porque não há um
// texto livre de origem sendo citado (isso só existe logo após a extração da Task 3; edição
// manual na revisão é uma fonte de verdade própria, não precisa de comprovação por substring).
export function campoEditado<T>(valor: T): CampoFicha<T> {
  return { valor, origem: "FORNECIDO", trecho: "" };
}

export interface AlertaFicha {
  codigo: string;
  severidade: string;
  campo: string;
  mensagem: string;
}

// Resultado do cálculo do preço sugerido (fichas_precificacao.calcular), recalculado a cada
// leitura/escrita -- nunca persistido (Fase 14, Bloco P, Task 19). "calculavel: false" +
// "motivo" no lugar de um número quando os custos/parâmetros não permitem calcular.
export interface PrecificacaoCalculada {
  calculavel: boolean;
  motivo: string;
  preco_sugerido: number | null;
  custo_total: number | null;
  categorias_informadas: Record<string, number>;
  categorias_ausentes: string[];
  parametros: PrecificacaoFicha;
  percentual_total: number | null;
  divisor: number | null;
}

// Envelope devolvido por toda rota que lê/escreve uma ficha específica -- os alertas e a
// precificação calculada são recalculados no backend a cada chamada, nunca um snapshot congelado
// (api/main.py:_ficha_com_alertas).
export interface FichaComAlertas {
  ficha: Ficha;
  alertas: AlertaFicha[];
  precificacao_calculada: PrecificacaoCalculada;
}

// ── Logo da empresa ──────────────────────────────────────────────────────────
// Cadastrado uma vez e reaproveitado em toda ficha gerada. Upload/remoção são operações de
// admin (mesma natureza da configuração do tenant); só a leitura é aberta, para a prévia.
export interface InfoLogo {
  cadastrado: boolean;
  metadados: {
    nome_original: string;
    formato_origem: string;
    largura_px: number;
    altura_px: number;
  } | null;
}

export async function obterInfoLogo(tenantId: string): Promise<InfoLogo> {
  return request<InfoLogo>(`/branding/logo/info?tenant_id=${encodeURIComponent(tenantId)}`);
}

// `versao` força o navegador a rebuscar a imagem depois de um upload -- sem isso, a prévia
// continuaria mostrando o logo antigo, que fica cacheado na mesma URL.
export function urlLogo(tenantId: string, versao?: string | number): string {
  const base = `${API_URL}/branding/logo?tenant_id=${encodeURIComponent(tenantId)}`;
  return versao === undefined ? base : `${base}&v=${encodeURIComponent(String(versao))}`;
}

export async function uploadLogo(tenantId: string, arquivo: File, tokenAdmin: string): Promise<InfoLogo["metadados"]> {
  const formData = new FormData();
  formData.append("arquivo", arquivo);

  const res = await fetch(`${API_URL}/branding/logo?tenant_id=${encodeURIComponent(tenantId)}`, {
    method: "POST",
    headers: { "X-Admin-Token": tokenAdmin, ...headerDeAcesso() },
    body: formData,
  });

  if (!res.ok) {
    throw await erroDaResposta(res);
  }

  return res.json() as Promise<InfoLogo["metadados"]>;
}

export async function deletarLogo(tenantId: string, tokenAdmin: string): Promise<void> {
  await request<{ status: string }>(`/branding/logo?tenant_id=${encodeURIComponent(tenantId)}`, {
    method: "DELETE",
    headers: { "X-Admin-Token": tokenAdmin },
  });
}

export async function listarFichas(tenantId: string): Promise<FichaResumo[]> {
  return request<FichaResumo[]>(`/fichas?tenant_id=${encodeURIComponent(tenantId)}`);
}

export async function criarFicha(tenantId: string, textoOrigem?: string): Promise<FichaComAlertas> {
  return request<FichaComAlertas>("/fichas", {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId, texto_origem: textoOrigem || null }),
  });
}

export async function obterFicha(tenantId: string, fichaId: string): Promise<FichaComAlertas> {
  return request<FichaComAlertas>(
    `/fichas/${encodeURIComponent(fichaId)}?tenant_id=${encodeURIComponent(tenantId)}`
  );
}

// atualizadoEmEsperado é o timestamp que o cliente tinha ao carregar a ficha para edição --
// divergência do valor salvo em disco vira HTTP 412 (fichas_repo.ConflitoDeVersaoError no
// backend), indicando que outra aba/sessão salvou a ficha nesse meio-tempo. O chamador (Task 8)
// trata ApiError com status 412 mostrando isso ao usuário em vez de sobrescrever silenciosamente.
export async function atualizarFicha(
  tenantId: string,
  ficha: Ficha,
  atualizadoEmEsperado?: string
): Promise<FichaComAlertas> {
  return request<FichaComAlertas>(`/fichas/${encodeURIComponent(ficha.id)}`, {
    method: "PUT",
    body: JSON.stringify({
      tenant_id: tenantId,
      ficha,
      atualizado_em_esperado: atualizadoEmEsperado ?? null,
    }),
  });
}

export async function duplicarFicha(tenantId: string, fichaId: string): Promise<FichaComAlertas> {
  return request<FichaComAlertas>(`/fichas/${encodeURIComponent(fichaId)}/duplicar`, {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId }),
  });
}

// URL do PDF de pré-visualização -- usada como `src` de um <iframe>, não via fetch. O backend
// não marca a ficha como emitida ao servir essa rota (diferente de /pdf), então abrir a prévia
// nunca muda o status de "Rascunho" para "Documento gerado".
export function urlPreviewFicha(tenantId: string, fichaId: string): string {
  return `${API_URL}/fichas/${encodeURIComponent(fichaId)}/preview?tenant_id=${encodeURIComponent(tenantId)}`;
}

// Gera o documento da ficha e dispara o download no navegador. É renderizado na hora, a cada
// chamada -- a ficha pode ter mudado desde a última geração, e entregar um arquivo desatualizado
// sem avisar seria pior que renderizar de novo. O PDF sai do mesmo .docx (convertido pelo
// LibreOffice), então os dois arquivos são visualmente idênticos.
export async function baixarFichaDocumento(
  tenantId: string,
  fichaId: string,
  formato: "docx" | "pdf"
): Promise<void> {
  const url = `${API_URL}/fichas/${encodeURIComponent(fichaId)}/${formato}?tenant_id=${encodeURIComponent(tenantId)}`;

  // Fase 15, V3: esta rota deixou de ser isenta do gate de acesso (nunca precisou ser -- o
  // fetch() já suporta header customizado, diferente de um <a href> apontando direto pra URL da
  // API). Sem o header aqui, um gate ligado devolveria 401 pra todo mundo.
  const res = await fetch(url, { headers: headerDeAcesso() });
  if (!res.ok) {
    throw await erroDaResposta(res);
  }

  // O nome vem do Content-Disposition montado pelo backend (ex: ficha_CM-001_Camisa.docx), que
  // é bem mais util na pasta de downloads do que o uuid da ficha.
  const disposicao = res.headers.get("Content-Disposition") ?? "";
  const nomeDoHeader = /filename="([^"]+)"/.exec(disposicao)?.[1];

  const blob = await res.blob();
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = nomeDoHeader || `ficha.${formato}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

// ── Desenho técnico (Fase 11, Task 17) ───────────────────────────────────────
// Recurso opt-in: `desenho.solicitado` só controla se a seção aparece no editor, sem custo
// nenhum -- a chamada de API de verdade só acontece quando o usuário clica em "Gerar" (gerarDesenho).
export function urlDesenho(tenantId: string, fichaId: string, versao: number): string {
  return `${API_URL}/fichas/${encodeURIComponent(fichaId)}/desenho/${versao}?tenant_id=${encodeURIComponent(tenantId)}`;
}

// ── Galeria de croquis (Fase 14, Bloco G, Task 15/16) ────────────────────────
export function urlCroqui(tenantId: string, croquiId: string): string {
  return `${API_URL}/croquis/${encodeURIComponent(croquiId)}/imagem?tenant_id=${encodeURIComponent(tenantId)}`;
}

export interface CroquiResumo {
  id: string;
  estilo: string;
  resumo: string;
  criado_em: string;
}

export async function listarCroquis(tenantId: string): Promise<CroquiResumo[]> {
  return request<CroquiResumo[]>(`/croquis?tenant_id=${encodeURIComponent(tenantId)}`);
}

export async function deletarCroqui(tenantId: string, croquiId: string, tokenAdmin: string): Promise<void> {
  await request<{ status: string }>(
    `/croquis/${encodeURIComponent(croquiId)}?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "DELETE", headers: { "X-Admin-Token": tokenAdmin } }
  );
}

// `instrucaoAdicional` é o pedido de ajuste da regeneração (ex: "a manga é 3/4, não curta") --
// omitido na primeira geração. O backend acumula sobre as instruções de versões anteriores, já
// que gpt-image-1 não tem seed/determinismo: cada geração é uma peça nova, nunca uma correção
// pontual da anterior.
export async function gerarDesenho(
  tenantId: string,
  fichaId: string,
  instrucaoAdicional?: string
): Promise<FichaComAlertas> {
  return request<FichaComAlertas>(`/fichas/${encodeURIComponent(fichaId)}/desenho`, {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId, instrucao_adicional: instrucaoAdicional || null }),
  });
}

// Sem custo de API -- só muda o estado persistido da ficha. Aprovar uma versão rebaixa
// automaticamente qualquer outra que estivesse aprovada (só uma vale por vez).
export async function aprovarDesenho(tenantId: string, fichaId: string, versao: number): Promise<FichaComAlertas> {
  return request<FichaComAlertas>(`/fichas/${encodeURIComponent(fichaId)}/desenho/${versao}/aprovar`, {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId }),
  });
}

// Aprovação (Fase 14, Bloco AP). `atualizadoEmEsperado` é obrigatório de propósito: aprovar é
// declarar "conferi esta versão", então uma ficha que mudou desde que a tela carregou devolve 412
// em vez de registrar o nome da pessoa embaixo de um conteúdo que ela não leu.
export async function aprovarFicha(
  tenantId: string,
  fichaId: string,
  aprovadaPor: string,
  atualizadoEmEsperado: string,
  observacao?: string
): Promise<FichaComAlertas> {
  return request<FichaComAlertas>(`/fichas/${encodeURIComponent(fichaId)}/aprovar`, {
    method: "POST",
    body: JSON.stringify({
      tenant_id: tenantId,
      aprovada_por: aprovadaPor,
      atualizado_em_esperado: atualizadoEmEsperado,
      observacao: observacao || null,
    }),
  });
}

export async function reabrirFicha(
  tenantId: string,
  fichaId: string,
  reabertaPor: string,
  observacao?: string
): Promise<FichaComAlertas> {
  return request<FichaComAlertas>(`/fichas/${encodeURIComponent(fichaId)}/reabrir`, {
    method: "POST",
    body: JSON.stringify({
      tenant_id: tenantId,
      reaberta_por: reabertaPor,
      observacao: observacao || null,
    }),
  });
}

// Reaproveita um croqui já salvo na galeria como versão do desenho técnico -- sem moderação, sem
// cota, sem chamada de API (Fase 14, Bloco G, Task 17): a imagem já foi moderada e cobrada quando
// foi gerada no chat.
export async function importarCroquiComoDesenho(tenantId: string, fichaId: string, croquiId: string): Promise<FichaComAlertas> {
  return request<FichaComAlertas>(`/fichas/${encodeURIComponent(fichaId)}/desenho/importar-croqui`, {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId, croqui_id: croquiId }),
  });
}

export async function deletarFicha(tenantId: string, fichaId: string, tokenAdmin: string): Promise<void> {
  await request<{ status: string }>(
    `/fichas/${encodeURIComponent(fichaId)}?tenant_id=${encodeURIComponent(tenantId)}`,
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

  // Fase 15, V3: mesma correção de baixarFichaDocumento -- esta rota deixou de ser isenta do
  // gate (devolvia o histórico completo da conversa sem credencial nenhuma).
  const res = await fetch(url, { headers: headerDeAcesso() });
  if (!res.ok) {
    throw await erroDaResposta(res);
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
