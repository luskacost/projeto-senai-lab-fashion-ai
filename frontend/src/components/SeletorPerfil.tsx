"use client";

import { useState } from "react";
import { UserCircle, X } from "lucide-react";
import { PERFIS, obterPerfilInfo } from "@/lib/perfis";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";

interface Props {
  perfilAtivo: string | null;
  onSelecionar: (perfil: string) => void;
  onLimpar: () => void;
}

export default function SeletorPerfil({ perfilAtivo, onSelecionar, onLimpar }: Props) {
  const [aberto, setAberto] = useState(false);
  const infoAtiva = obterPerfilInfo(perfilAtivo);
  const IconeAtivo = infoAtiva?.icone ?? UserCircle;

  return (
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger
        className="flex items-center gap-1.5 rounded-lg bg-muted px-2.5 py-1.5 text-sm text-foreground hover:bg-muted/70"
        aria-label="Escolher perfil"
        title={infoAtiva ? `Perfil ativo: ${infoAtiva.nome}` : "Escolher perfil (opcional)"}
      >
        <IconeAtivo className="h-4 w-4" />
        {infoAtiva && <span className="font-medium">{infoAtiva.nome}</span>}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-2">
        <div className="flex flex-col gap-1">
          <p className="px-2 pt-1 pb-0.5 text-xs text-muted-foreground">
            Qual é o seu papel na empresa? Isso personaliza o modo padrão, as sugestões e o tom das respostas -- todos os modos continuam disponíveis de qualquer forma.
          </p>
          {PERFIS.map((perfil) => {
            const selecionado = perfil.id === perfilAtivo;
            const Icone = perfil.icone;
            return (
              <Button
                key={perfil.id}
                variant={selecionado ? "secondary" : "ghost"}
                className="h-auto justify-start gap-2.5 whitespace-normal px-2.5 py-2 text-left font-normal"
                onClick={() => {
                  onSelecionar(perfil.id);
                  setAberto(false);
                }}
              >
                <Icone className="h-5 w-5 shrink-0" />
                <span className="min-w-0">
                  <span
                    className={`block text-sm font-medium ${selecionado ? "text-secondary-foreground" : "text-foreground"}`}
                  >
                    {perfil.nome}
                  </span>
                  <span
                    className={`block text-xs ${selecionado ? "text-secondary-foreground/75" : "text-muted-foreground"}`}
                  >
                    {perfil.descricao}
                  </span>
                </span>
              </Button>
            );
          })}
          {perfilAtivo && (
            <>
              <Separator className="my-1" />
              <Button
                variant="ghost"
                className="h-auto justify-start gap-2.5 px-2.5 py-2 text-left font-normal text-muted-foreground"
                onClick={() => {
                  onLimpar();
                  setAberto(false);
                }}
              >
                <X className="h-4 w-4 shrink-0" />
                <span className="text-sm">Remover perfil</span>
              </Button>
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
