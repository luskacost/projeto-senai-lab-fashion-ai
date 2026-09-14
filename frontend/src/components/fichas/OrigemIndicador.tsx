"use client";

import { OrigemCampo } from "@/lib/api";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

// Regra de não-invenção do produto, na prática: todo campo carrega de onde o valor veio
// (fichas_modelo.py, backend). Este ponto colorido por campo é a única superfície onde essa
// proveniência aparece pro usuário -- sem ele, um "número de moldes" inferido pela IA fica
// indistinguível de um que o usuário realmente informou.
const ROTULO_ORIGEM: Record<OrigemCampo, string> = {
  FORNECIDO: "Informado",
  OBSERVADO: "Observado em anexo",
  INFERIDO: "Deduzido pela IA — confira antes de confiar",
  DESCONHECIDO: "Sem informação",
};

const COR_ORIGEM: Record<OrigemCampo, string> = {
  FORNECIDO: "bg-emerald-500",
  OBSERVADO: "bg-sky-500",
  INFERIDO: "bg-amber-500",
  DESCONHECIDO: "bg-muted-foreground/25",
};

export default function OrigemIndicador({ origem, trecho }: { origem: OrigemCampo; trecho?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger className="inline-flex shrink-0 items-center rounded-full bg-transparent p-0.5 appearance-none">
        <span className={`h-1.5 w-1.5 rounded-full ${COR_ORIGEM[origem]}`} aria-hidden />
        <span className="sr-only">{ROTULO_ORIGEM[origem]}</span>
      </TooltipTrigger>
      <TooltipContent>
        <div className="space-y-0.5">
          <p>{ROTULO_ORIGEM[origem]}</p>
          {trecho && <p className="italic opacity-80">&ldquo;{trecho}&rdquo;</p>}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
