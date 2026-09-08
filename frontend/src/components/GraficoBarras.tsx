import type { GraficoBarrasDados } from "@/lib/api";

function formatarNumero(valor: number): string {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(valor);
}

// Ranking de magnitude (série única) em barras horizontais: sem legenda (o título já diz o que é
// plotado), rótulo direto de categoria + valor (nunca só na cor), barra com ponta arredondada
// ancorada na base, cor primária fixa da marca (uma série não precisa de paleta categórica).
export default function GraficoBarras({ dados }: { dados: GraficoBarrasDados }) {
  if (!dados.itens.length) return null;
  const maximo = Math.max(...dados.itens.map((i) => i.valor), 1);

  return (
    <div className="mt-1.5 w-full max-w-sm rounded-lg border border-border bg-card p-3">
      <p className="mb-2.5 text-xs font-medium text-muted-foreground">{dados.titulo}</p>
      <div className="space-y-2">
        {dados.itens.map((item) => (
          <div key={item.rotulo} className="group">
            <div className="mb-0.5 flex items-baseline justify-between gap-2">
              <span className="truncate text-xs text-foreground" title={item.rotulo}>
                {item.rotulo}
              </span>
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                {formatarNumero(item.valor)}
              </span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-sm bg-muted">
              <div
                className="h-full rounded-r bg-primary transition-opacity group-hover:opacity-80"
                style={{ width: `${Math.max((item.valor / maximo) * 100, 2)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
