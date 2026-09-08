"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { MODOS, obterModoInfo } from "@/lib/modos";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

interface Props {
  modoAtivo: string;
  onSelecionar: (modo: string) => void;
}

export default function SeletorModo({ modoAtivo, onSelecionar }: Props) {
  const [aberto, setAberto] = useState(false);
  const infoAtivo = obterModoInfo(modoAtivo);

  return (
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger
        className="flex items-center gap-1.5 rounded-lg bg-muted px-2.5 py-1.5 text-sm text-foreground hover:bg-muted/70"
      >
        <span>{infoAtivo?.emoji}</span>
        <span className="font-medium">{infoAtivo?.id ?? modoAtivo}</span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-2">
        <div className="flex flex-col gap-1">
          {MODOS.map((modo) => (
            <Button
              key={modo.id}
              variant={modo.id === modoAtivo ? "secondary" : "ghost"}
              className="h-auto justify-start gap-2.5 whitespace-normal px-2.5 py-2 text-left font-normal"
              onClick={() => {
                onSelecionar(modo.id);
                setAberto(false);
              }}
            >
              <span className="text-lg shrink-0">{modo.emoji}</span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">{modo.id}</span>
                <span className="block text-xs text-muted-foreground">{modo.descricao}</span>
              </span>
            </Button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
