import { StatusFicha } from "./api";

export const ROTULO_STATUS_FICHA: Record<StatusFicha, string> = {
  RASCUNHO: "Rascunho",
  EM_REVISAO: "Em revisão",
  DESENHO_GERADO: "Desenho gerado",
  AGUARDANDO_APROVACAO: "Aguardando aprovação",
  APROVADA: "Aprovada",
  DOCUMENTO_GERADO: "Documento gerado",
};

// "default" (cor primária) pros estados que pedem atenção/ação do usuário; "secondary" pros
// estados intermediários/concluídos; "outline" pro rascunho, o mais neutro de todos.
export const VARIANTE_STATUS_FICHA: Record<StatusFicha, "default" | "secondary" | "outline"> = {
  RASCUNHO: "outline",
  EM_REVISAO: "secondary",
  DESENHO_GERADO: "secondary",
  AGUARDANDO_APROVACAO: "default",
  APROVADA: "default",
  DOCUMENTO_GERADO: "secondary",
};
