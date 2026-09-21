// Modos de atuação do assistente, espelhados de tenant_config.py
// (TENANT_CONFIG["senai_labfashion"]["descricoes_modos"] / "descricoes_detalhadas").
// Fixo no código, mesmo padrão de branding.ts -- não é mais buscado do /config/tenant.

import { BarChart3, BookOpen, Bot, FlaskConical, LucideIcon, Palette, Ruler, Shirt, TrendingUp } from "lucide-react";

export interface ModoInfo {
  id: string;
  icone: LucideIcon;
  categoria: string;
  descricao: string;
}

export const MODOS: ModoInfo[] = [
  {
    id: "Base de Conhecimento",
    icone: BookOpen,
    categoria: "Materiais e Manuais",
    descricao: "Pergunte sobre os materiais e documentos que a empresa disponibilizou (apostilas, manuais, fichas técnicas).",
  },
  {
    id: "Gerador de Croqui",
    icone: Palette,
    categoria: "Desenho e Croquis",
    descricao: "Cria conceitos visuais em 2 estilos: Ilustração de Moda (conceito artístico) ou Desenho Técnico / Flat Sketch (diagrama 2D com vistas frontal e traseira).",
  },
  {
    id: "Consultor de Estilo",
    icone: Shirt,
    categoria: "Estilo e Looks",
    descricao: "Focado em combinações, harmonia de cores, looks e consultoria de imagem pessoal.",
  },
  {
    id: "Professor Técnico",
    icone: Ruler,
    categoria: "Costura e Modelagem",
    descricao: "Especializado em costura, modelagem, tecidos e processos têxteis.",
  },
  {
    id: "Engenharia Têxtil",
    icone: FlaskConical,
    categoria: "Normas e Ensaios",
    descricao: "Normas técnicas (ABNT/ISO), ensaios de tecido, controle de qualidade e processos industriais de beneficiamento e tingimento.",
  },
  {
    id: "Tendências",
    icone: TrendingUp,
    categoria: "Consumo e Mercado",
    descricao: "Analisa comportamento de consumo, desfiles e previsões de mercado.",
  },
  {
    id: "Análise de Dados",
    icone: BarChart3,
    categoria: "Planilhas e Indicadores",
    descricao: "Envie uma planilha de vendas, estoque ou produção e faça perguntas sobre os números.",
  },
  {
    id: "Assistente Geral",
    icone: Bot,
    categoria: "Qualquer assunto",
    descricao: "Converse sobre qualquer assunto, sem restrição de escopo a moda -- como o ChatGPT ou o Claude.",
  },
];

export const MODOS_DISPONIVEIS = MODOS.map((m) => m.id);

// Modo inicial para quem ainda não escolheu um perfil (Fase 14, Bloco U, Task 5) -- antes, o chat
// sempre começava em MODOS_DISPONIVEIS[0] ("Base de Conhecimento"), que só funciona depois que um
// admin sobe documentos em /admin. Um usuário novo caía direto num modo que, sem nenhuma
// explicação, respondia "não encontrei nos documentos" para qualquer pergunta. "Consultor de
// Estilo" não depende de nenhuma configuração prévia -- funciona de imediato para qualquer
// pessoa. A escolha de perfil continua opcional e pulável (decisão da Fase 6): isto só muda o
// ponto de partida de quem nunca escolheu um.
export const MODO_PADRAO_SEM_PERFIL = "Consultor de Estilo";

// Modos que rodam via chamar_agente() no backend (tool calling) e por isso se beneficiam
// de receber o histórico completo da conversa a cada chamada -- ao contrário de
// "Base de Conhecimento" (usa buscar_contexto_relevante + conversation_id) e
// "Análise de Dados" (usa o resumo estatístico persistido, não o histórico de chat).
export function ehModoDeAgente(modo: string): boolean {
  return modo !== "Base de Conhecimento" && modo !== "Análise de Dados";
}

export function obterModoInfo(modo: string): ModoInfo | undefined {
  return MODOS.find((m) => m.id === modo);
}
