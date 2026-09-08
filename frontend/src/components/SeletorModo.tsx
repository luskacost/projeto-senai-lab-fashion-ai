"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { MODOS, obterModoInfo } from "@/lib/modos";
import { MODOS_RELEVANTES_POR_PERFIL, PerfilId } from "@/lib/perfis";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";

interface Props {
  modoAtivo: string;
  perfilAtivo?: string | null;
  onSelecionar: (modo: string) => void;
}

function renderizarCard(
  modo: (typeof MODOS)[number],
  selecionado: boolean,
  recomendado: boolean,
  onClick: () => void
) {
  const Icone = modo.icone;
  return (
    <Button
      key={modo.id}
      variant={selecionado ? "secondary" : "ghost"}
      className="h-auto justify-start gap-2.5 whitespace-normal px-2.5 py-2 text-left font-normal"
      onClick={onClick}
    >
      <Icone className="h-5 w-5 shrink-0" />
      <span className="min-w-0">
        <span
          className={`flex items-center gap-1.5 text-sm font-medium ${selecionado ? "text-secondary-foreground" : "text-foreground"}`}
        >
          {modo.id}
          {recomendado && <Badge className="font-normal">Recomendado</Badge>}
        </span>
        <span
          className={`block text-xs ${selecionado ? "text-secondary-foreground/75" : "text-muted-foreground"}`}
        >
          {modo.descricao}
        </span>
      </span>
    </Button>
  );
}

export default function SeletorModo({ modoAtivo, perfilAtivo, onSelecionar }: Props) {
  const [aberto, setAberto] = useState(false);
  const infoAtivo = obterModoInfo(modoAtivo);
  const IconeAtivo = infoAtivo?.icone;

  const relevantes = perfilAtivo ? MODOS_RELEVANTES_POR_PERFIL[perfilAtivo as PerfilId] : undefined;
  const modosRecomendados = relevantes ? relevantes.map((id) => obterModoInfo(id)).filter((m) => m !== undefined) : [];
  const modosRestantes = relevantes ? MODOS.filter((m) => !relevantes.includes(m.id)) : MODOS;

  function selecionar(modoId: string) {
    onSelecionar(modoId);
    setAberto(false);
  }

  return (
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger
        className="flex items-center gap-1.5 rounded-lg bg-muted px-2.5 py-1.5 text-sm text-foreground hover:bg-muted/70"
      >
        {IconeAtivo && <IconeAtivo className="h-4 w-4" />}
        <span className="font-medium">{infoAtivo?.id ?? modoAtivo}</span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-2">
        <div className="flex flex-col gap-1">
          {modosRecomendados.length > 0 && (
            <>
              {modosRecomendados.map((modo) =>
                renderizarCard(modo!, modo!.id === modoAtivo, true, () => selecionar(modo!.id))
              )}
              <Separator className="my-1" />
            </>
          )}
          {modosRestantes.map((modo) => renderizarCard(modo, modo.id === modoAtivo, false, () => selecionar(modo.id)))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
