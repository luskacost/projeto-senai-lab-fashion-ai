"use client";

import { useState } from "react";
import { History, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { cn } from "cn";
import { Conversa } from "@/lib/api";
import { buttonVariants } from "@/components/ui/button";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface Props {
  conversas: Conversa[];
  conversaAtualId: string | null;
  onSelecionar: (id: string) => void;
  onNovaConversa: () => void;
  onRenomear: (id: string, novoTitulo: string) => void;
  onDeletar: (id: string) => void;
}

export default function ConversasHistorico({
  conversas,
  conversaAtualId,
  onSelecionar,
  onNovaConversa,
  onRenomear,
  onDeletar,
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [editandoId, setEditandoId] = useState<string | null>(null);
  const [tituloEmEdicao, setTituloEmEdicao] = useState("");

  const conversasOrdenadas = [...conversas].sort(
    (a, b) => new Date(b.atualizado_em).getTime() - new Date(a.atualizado_em).getTime()
  );

  function iniciarEdicao(conv: Conversa) {
    setEditandoId(conv.id);
    setTituloEmEdicao(conv.titulo);
  }

  function confirmarEdicao(id: string) {
    const titulo = tituloEmEdicao.trim();
    if (titulo) {
      onRenomear(id, titulo);
    }
    setEditandoId(null);
  }

  function confirmarExclusao(id: string) {
    if (window.confirm("Excluir esta conversa? Essa ação não pode ser desfeita.")) {
      onDeletar(id);
    }
  }

  function selecionarEFechar(id: string) {
    onSelecionar(id);
    setAberto(false);
  }

  return (
    <Sheet open={aberto} onOpenChange={setAberto}>
      <SheetTrigger
        className={cn(buttonVariants({ variant: "ghost", size: "icon" }), "size-11")}
        aria-label="Histórico de conversas"
        title="Histórico de conversas"
      >
        <History className="h-4 w-4" />
      </SheetTrigger>

      <SheetContent side="left" className="w-3/4 sm:max-w-xs p-0">
        <SheetHeader className="border-b border-border">
          <SheetTitle>Conversas</SheetTitle>
        </SheetHeader>

        <div className="px-4">
          <Button
            onClick={() => {
              onNovaConversa();
              setAberto(false);
            }}
            className="w-full"
          >
            <Plus className="h-4 w-4" />
            Nova conversa
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-1">
          {conversasOrdenadas.length === 0 && (
            <p className="text-center text-muted-foreground text-xs mt-4 px-2">Nenhuma conversa ainda.</p>
          )}

          {conversasOrdenadas.map((conv) => {
            const ativa = conv.id === conversaAtualId;
            return (
              <div
                key={conv.id}
                className={`group rounded-lg px-2 py-2 cursor-pointer text-sm flex items-center justify-between gap-1 ${
                  ativa ? "bg-accent text-accent-foreground" : "hover:bg-muted text-foreground"
                }`}
                onClick={() => editandoId !== conv.id && selecionarEFechar(conv.id)}
              >
                {editandoId === conv.id ? (
                  <input
                    autoFocus
                    value={tituloEmEdicao}
                    onChange={(e) => setTituloEmEdicao(e.target.value)}
                    onBlur={() => confirmarEdicao(conv.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") confirmarEdicao(conv.id);
                      if (e.key === "Escape") setEditandoId(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="flex-1 rounded border border-ring bg-background px-1 py-0.5 text-sm"
                  />
                ) : (
                  <span className="flex-1 truncate">{conv.titulo}</span>
                )}

                {editandoId !== conv.id && (
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      className={buttonVariants({
                        variant: "ghost",
                        size: "icon-sm",
                        // "opacity-0 group-hover:opacity-100" (revelar só no hover do mouse) deixa
                        // este botão praticamente inalcançável em touch, que não tem hover --
                        // sempre visível abaixo de sm: (Fase 14, Bloco U, Task 6), hover-reveal
                        // preservado em telas largas por estética (lista mais "limpa" no mouse).
                        className: "size-11 shrink-0 opacity-100 sm:size-7 sm:opacity-0 sm:group-hover:opacity-100 sm:data-popup-open:opacity-100",
                      })}
                      onClick={(e: React.MouseEvent) => e.stopPropagation()}
                      aria-label="Ações da conversa"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="end"
                      onClick={(e: React.MouseEvent) => e.stopPropagation()}
                      // Sem isso, o Base UI devolve o foco pro botão "..." ao fechar o menu --
                      // colidindo com o autoFocus do input de renomear (que abre em resposta ao
                      // mesmo clique) e disparando um blur imediato nele, que por sua vez chama
                      // confirmarEdicao() antes do usuário digitar qualquer coisa. Era esse race
                      // que fazia "Renomear" parecer não fazer nada (bug relatado pelo usuário).
                      finalFocus={false}
                    >
                      <DropdownMenuItem onClick={() => iniciarEdicao(conv)}>
                        <Pencil className="h-4 w-4" />
                        Renomear
                      </DropdownMenuItem>
                      <DropdownMenuItem variant="destructive" onClick={() => confirmarExclusao(conv.id)}>
                        <Trash2 className="h-4 w-4" />
                        Excluir
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
