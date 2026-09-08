// Perfis de usuário dentro de uma empresa de moda, espelhados de tenant_config.py
// (PERFIS_USUARIO, modo_padrao_por_perfil, perguntas_por_perfil). Fixo no código, mesmo
// padrão de branding.ts/modos.ts -- não é mais buscado do /config/tenant.
//
// Perfil é só personalização (modo padrão, sugestões, tom da resposta) e destaque visual
// dos modos mais relevantes -- nunca restringe o acesso a nenhum modo.

import { Briefcase, Factory, LucideIcon, Sparkles } from "lucide-react";

export type PerfilId = "dono_responsavel" | "producao" | "criacao_estilo";

export interface PerfilInfo {
  id: PerfilId;
  nome: string;
  icone: LucideIcon;
  descricao: string;
  rotuloPrompt: string;
}

export const PERFIS: PerfilInfo[] = [
  {
    id: "dono_responsavel",
    nome: "Dono(a) / Responsável",
    icone: Briefcase,
    descricao: "Visão geral do negócio, custos e estratégias",
    rotuloPrompt: "Dono(a) ou Responsável Geral pela empresa de moda",
  },
  {
    id: "producao",
    nome: "Time de Produção",
    icone: Factory,
    descricao: "Modelagem, tecidos, costura e processos técnicos",
    rotuloPrompt: "integrante do Time de Produção (modelagem, tecidos, costura e processos técnicos)",
  },
  {
    id: "criacao_estilo",
    nome: "Criação / Estilo",
    icone: Sparkles,
    descricao: "Croquis, tendências, estética e conceito de coleção",
    rotuloPrompt: "integrante do Time de Criação e Estilo (croquis, tendências e conceito de coleção)",
  },
];

export const MODO_PADRAO_POR_PERFIL: Record<PerfilId, string> = {
  dono_responsavel: "Análise de Dados",
  producao: "Professor Técnico",
  criacao_estilo: "Gerador de Croqui",
};

// Modos priorizados/destacados para cada perfil no seletor de modo (soft -- todos os
// modos continuam acessíveis, isso só afeta ordem/destaque visual).
export const MODOS_RELEVANTES_POR_PERFIL: Record<PerfilId, string[]> = {
  dono_responsavel: ["Análise de Dados", "Tendências", "Base de Conhecimento"],
  producao: ["Professor Técnico", "Base de Conhecimento", "Análise de Dados"],
  criacao_estilo: ["Gerador de Croqui", "Consultor de Estilo", "Tendências"],
};

export const PERGUNTAS_POR_PERFIL: Record<PerfilId, Record<string, string[]>> = {
  dono_responsavel: {
    "Análise de Dados": [
      "Qual o total acumulado e a média dos valores na planilha?",
      "Quais categorias ou produtos têm maior volume de ocorrências?",
      "Quais são os valores mínimos e máximos identificados?",
    ],
    "Tendências": [
      "Quais as principais tendências de consumo para a próxima estação?",
      "Como otimizar custos de coleção mantendo o valor percebido?",
      "Qual o impacto das macro-tendências globais no mercado de moda?",
    ],
    "Consultor de Estilo": [
      "Como posicionar o estilo da marca para o nosso público-alvo?",
      "Quais combinações de cores agregam mais valor comercial?",
      "Como adequar o mix de produtos aos biotipos dos clientes?",
    ],
    "Professor Técnico": [
      "Como avaliar o custo-benefício e viabilidade de novos tecidos?",
      "Quais gargalos técnicos mais afetam o prazo de entrega?",
      "Como padronizar o controle de qualidade na confecção?",
    ],
    "Gerador de Croqui": [
      "Conceito visual de coleção executiva minimalista.",
      "Ideias de croqui para linha premium da marca.",
      "Como transmitir sofisticação comercial através dos croquis?",
    ],
    "Base de Conhecimento": [
      "Quais normas e manuais internos da empresa constam nos materiais?",
      "Quais diretrizes estratégicas e de qualidade estão descritas nos documentos?",
      "Resuma os principais procedimentos operacionais documentados.",
    ],
  },
  producao: {
    "Professor Técnico": [
      "Qual agulha e linha ideais para tecidos planos finos?",
      "Como calcular o consumo e encaixe de tecido com precisão?",
      "Qual a diferença prática entre urdume e trama na costura?",
    ],
    "Análise de Dados": [
      "Qual a média e o volume total dos itens registrados?",
      "Quais tipos de materiais ou produtos aparecem com mais frequência?",
      "Há registros com quantidades mínimas ou pontos de atenção?",
    ],
    "Gerador de Croqui": [
      "Como traduzir um croqui complexo em ficha técnica de modelagem?",
      "Prompt para croqui técnico focado em detalhes de costura.",
      "Como visualizar caimento de tecido pesado em croqui?",
    ],
    "Consultor de Estilo": [
      "Quais tecidos proporcionam melhor caimento para cada biotipo?",
      "Como garantir a vestibilidade mantendo a proposta de estilo?",
      "Quais acabamentos agregam melhor estrutura ao look?",
    ],
    "Tendências": [
      "Quais tecidos sustentáveis estão em alta para produção?",
      "Novas tecnologias têxteis para aumento de durabilidade.",
      "Inovações em processos de tingimento e acabamento eco-friendly.",
    ],
    "Base de Conhecimento": [
      "Quais especificações técnicas de costura constam nas apostilas e manuais?",
      "Quais tabelas de medidas e moldes estão descritas nos documentos?",
      "Quais passos de montagem e acabamento são recomendados nas fichas?",
    ],
  },
  criacao_estilo: {
    "Gerador de Croqui": [
      "Croqui de vestido de festa fluido com movimento natural.",
      "Ideias inovadoras de silhueta para coleção outono/inverno.",
      "Prompt para conjunto alfaiataria moderno e desconstruído.",
    ],
    "Análise de Dados": [
      "Quais modelos ou categorias são mais frequentes na planilha?",
      "Como estão distribuídas as ocorrências por tipo de peça?",
      "Qual o volume total de itens cadastrados?",
    ],
    "Tendências": [
      "Cartela de cores e estampas em alta para a próxima estação.",
      "Macro-tendências de comportamento da Geração Z na moda.",
      "Como aplicar o conceito de upcycling na criação de modelos.",
    ],
    "Consultor de Estilo": [
      "Quais harmonias de cores valorizam estampas exclusivas?",
      "Sugestões de combinações de texturas para editorial de moda.",
      "Como compor looks versáteis para a nova coleção?",
    ],
    "Professor Técnico": [
      "Quais tecidos transmitem o caimento ideal para este design?",
      "Como viabilizar recortes complexos sem perder a estrutura?",
      "Técnicas de moulage para desenvolver formas orgânicas.",
    ],
    "Base de Conhecimento": [
      "Quais conceitos de coleção e diretrizes criativas estão nos documentos?",
      "O que as apostilas internas descrevem sobre harmonia e estética?",
      "Quais fichas de inspiração e referências foram cadastradas?",
    ],
  },
};

export function obterPerfilInfo(perfil: string | null): PerfilInfo | undefined {
  return PERFIS.find((p) => p.id === perfil);
}
