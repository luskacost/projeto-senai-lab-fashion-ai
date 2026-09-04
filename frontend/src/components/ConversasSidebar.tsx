"use client";

import { useState } from "react";
import { Conversa } from "@/lib/api";

interface Props {
  conversas: Conversa[];
  conversaAtualId: string | null;
  corPrimaria: string;
  onSelecionar: (id: string) => void;
  onNovaConversa: () => void;
  onRenomear: (id: string, novoTitulo: string) => void;
  onDeletar: (id: string) => void;
}

export default function ConversasSidebar({
  conversas,
  conversaAtualId,
  corPrimaria,
  onSelecionar,
  onNovaConversa,
  onRenomear,
  onDeletar,
}: Props) {
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

  return (
    <aside className="w-64 shrink-0 border-r border-gray-200 bg-white flex flex-col h-full">
      <div className="p-3">
        <button
          onClick={onNovaConversa}
          className="w-full rounded-lg text-white text-sm font-medium py-2 hover:opacity-90 transition"
          style={{ backgroundColor: corPrimaria }}
        >
          + Nova conversa
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
        {conversasOrdenadas.length === 0 && (
          <p className="text-center text-gray-400 text-xs mt-4 px-2">Nenhuma conversa ainda.</p>
        )}

        {conversasOrdenadas.map((conv) => {
          const ativa = conv.id === conversaAtualId;
          return (
            <div
              key={conv.id}
              className={`group rounded-lg px-2 py-2 cursor-pointer text-sm flex items-center justify-between gap-1 ${
                ativa ? "bg-blue-50 text-blue-900" : "hover:bg-gray-100 text-gray-700"
              }`}
              onClick={() => editandoId !== conv.id && onSelecionar(conv.id)}
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
                  className="flex-1 rounded border border-blue-300 px-1 py-0.5 text-sm"
                />
              ) : (
                <span className="flex-1 truncate">{conv.titulo}</span>
              )}

              {editandoId !== conv.id && (
                <div className="opacity-0 group-hover:opacity-100 flex gap-1 shrink-0 transition-opacity">
                  <button
                    title="Renomear"
                    onClick={(e) => {
                      e.stopPropagation();
                      iniciarEdicao(conv);
                    }}
                    className="text-gray-400 hover:text-gray-700 px-1"
                  >
                    ✏️
                  </button>
                  <button
                    title="Excluir"
                    onClick={(e) => {
                      e.stopPropagation();
                      confirmarExclusao(conv.id);
                    }}
                    className="text-gray-400 hover:text-red-600 px-1"
                  >
                    🗑️
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
