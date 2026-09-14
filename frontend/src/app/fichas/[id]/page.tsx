"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertaFicha,
  ApiError,
  Aviamento,
  CampoFicha,
  CorBeneficiamento,
  DadosFicha,
  Ficha,
  Operacao,
  Tecido,
  aviamentoVazio,
  atualizarFicha,
  campoEditado,
  corBeneficiamentoVazia,
  obterFicha,
  operacaoVazia,
  parteModelagemVazia,
  tecidoVazio,
} from "@/lib/api";
import { ROTULO_STATUS_FICHA, VARIANTE_STATUS_FICHA } from "@/lib/fichas-status";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import OrigemIndicador from "@/components/fichas/OrigemIndicador";
import { AlertTriangle, ArrowLeft, Loader2, Plus, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";

const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";

const TAMANHOS_NUMERICOS = ["34", "36", "38", "40", "42", "44", "46", "48", "50", "52", "54", "56"];
const TAMANHOS_COMERCIAIS = ["PP", "P", "M", "G", "GG", "XG"];

// ─── Campos escalares reutilizados nas 3 abas ──────────────────────────────────────────────────

function CampoTexto({
  id,
  label,
  campo,
  onChange,
  textarea = false,
}: {
  id: string;
  label: string;
  campo: CampoFicha<string>;
  onChange: (valor: string) => void;
  textarea?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <Label htmlFor={id}>{label}</Label>
        <OrigemIndicador origem={campo.origem} trecho={campo.trecho} />
      </div>
      {textarea ? (
        <Textarea id={id} value={campo.valor} onChange={(e) => onChange(e.target.value)} rows={3} />
      ) : (
        <Input id={id} value={campo.valor} onChange={(e) => onChange(e.target.value)} />
      )}
    </div>
  );
}

function CampoNumero({
  id,
  label,
  campo,
  onChange,
}: {
  id: string;
  label: string;
  campo: CampoFicha<number | null>;
  onChange: (valor: number | null) => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <Label htmlFor={id}>{label}</Label>
        <OrigemIndicador origem={campo.origem} trecho={campo.trecho} />
      </div>
      <Input
        id={id}
        type="number"
        step="0.01"
        value={campo.valor ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    </div>
  );
}

// Célula de tabela: mesma ideia dos campos acima, mas sem label própria (o cabeçalho da coluna
// já cumpre esse papel) e mais compacta.
function CelulaTexto({ campo, onChange }: { campo: CampoFicha<string>; onChange: (valor: string) => void }) {
  return (
    <div className="flex items-center gap-1">
      <Input value={campo.valor} onChange={(e) => onChange(e.target.value)} className="h-8 min-w-28 text-sm" />
      <OrigemIndicador origem={campo.origem} trecho={campo.trecho} />
    </div>
  );
}

function CelulaNumero({
  campo,
  onChange,
}: {
  campo: CampoFicha<number | null>;
  onChange: (valor: number | null) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <Input
        type="number"
        step="0.01"
        value={campo.valor ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        className="h-8 w-24 text-sm"
      />
      <OrigemIndicador origem={campo.origem} trecho={campo.trecho} />
    </div>
  );
}

export default function FichaDetalhePage() {
  const params = useParams<{ id: string }>();
  const fichaId = params.id;

  const [ficha, setFicha] = useState<Ficha | null>(null);
  // Vem junto do envelope de toda leitura/escrita (fichas_validacao.validar_ficha, backend) --
  // guardados à parte de `ficha` porque não fazem parte do documento persistido em si.
  const [alertas, setAlertas] = useState<AlertaFicha[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!fichaId) return;
    let cancelado = false;

    (async () => {
      setCarregando(true);
      setErro(null);
      try {
        const resultado = await obterFicha(TENANT_ID, fichaId);
        if (cancelado) return;
        setFicha(resultado.ficha);
        setAlertas(resultado.alertas);
      } catch (e) {
        if (cancelado) return;
        const msg = e instanceof ApiError ? e.message : "Falha ao carregar a ficha.";
        setErro(msg);
        toast.error(msg);
      } finally {
        if (!cancelado) setCarregando(false);
      }
    })();

    return () => {
      cancelado = true;
    };
  }, [fichaId]);

  // Toda edição passa por aqui: recebe a função que transforma "dados" e devolve a ficha inteira
  // atualizada, mantendo o resto do documento (id/status/timestamps/desenho/documentos) intacto.
  function atualizarDados(atualizar: (dados: DadosFicha) => DadosFicha) {
    setFicha((atual) => (atual ? { ...atual, dados: atualizar(atual.dados) } : atual));
  }

  async function salvar() {
    if (!ficha) return;
    setSalvando(true);
    try {
      const resultado = await atualizarFicha(TENANT_ID, ficha, ficha.atualizado_em);
      setFicha(resultado.ficha);
      setAlertas(resultado.alertas);
      toast.success("Ficha salva.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) {
        toast.error("Esta ficha foi alterada em outra sessão/aba. Recarregue a página para ver a versão mais recente antes de salvar de novo.");
      } else {
        toast.error(e instanceof ApiError ? e.message : "Falha ao salvar a ficha.");
      }
    } finally {
      setSalvando(false);
    }
  }

  if (carregando) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-6 p-6">
        <p className="text-sm text-muted-foreground">Carregando...</p>
      </div>
    );
  }

  if (erro || !ficha) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-6 p-6">
        <Link href="/fichas" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          Voltar às fichas
        </Link>
        <p className="text-sm text-destructive">{erro ?? "Ficha não encontrada."}</p>
      </div>
    );
  }

  const dados = ficha.dados;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 p-6">
      <div className="flex items-center justify-between gap-3">
        <Link href="/fichas" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          Voltar às fichas
        </Link>
        <div className="flex items-center gap-2">
          <Badge variant={VARIANTE_STATUS_FICHA[ficha.status]}>{ROTULO_STATUS_FICHA[ficha.status]}</Badge>
          <Button onClick={salvar} disabled={salvando}>
            {salvando ? <Loader2 className="animate-spin" /> : <Save />}
            {salvando ? "Salvando..." : "Salvar"}
          </Button>
        </div>
      </div>

      {alertas.length > 0 && (
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-primary" />
              Alertas ({alertas.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1">
              {alertas.map((a, i) => (
                <li key={`${a.codigo}-${i}`} className="text-sm text-muted-foreground">
                  • {a.mensagem}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="identificacao">
        <TabsList>
          <TabsTrigger value="identificacao">1. Identificação</TabsTrigger>
          <TabsTrigger value="materiais">2. Tamanhos e Custos</TabsTrigger>
          <TabsTrigger value="producao">3. Produção</TabsTrigger>
        </TabsList>

        {/* ─── PÁGINA 1: IDENTIFICAÇÃO DO PRODUTO + CORES/BENEFICIAMENTOS ────────────────── */}
        <TabsContent value="identificacao" className="space-y-6 pt-4">
          <Card>
            <CardHeader>
              <CardTitle>Identificação do produto</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <CampoTexto
                id="ref"
                label="Referência"
                campo={dados.ficha.ref}
                onChange={(v) => atualizarDados((d) => ({ ...d, ficha: { ...d.ficha, ref: campoEditado(v) } }))}
              />
              <CampoTexto
                id="nome"
                label="Nome"
                campo={dados.ficha.nome}
                onChange={(v) => atualizarDados((d) => ({ ...d, ficha: { ...d.ficha, nome: campoEditado(v) } }))}
              />
              <CampoTexto
                id="colecao"
                label="Coleção"
                campo={dados.ficha.colecao}
                onChange={(v) => atualizarDados((d) => ({ ...d, ficha: { ...d.ficha, colecao: campoEditado(v) } }))}
              />
              <CampoTexto
                id="designer"
                label="Designer"
                campo={dados.ficha.designer}
                onChange={(v) => atualizarDados((d) => ({ ...d, ficha: { ...d.ficha, designer: campoEditado(v) } }))}
              />
              <CampoTexto
                id="tecnica"
                label="Técnica"
                campo={dados.ficha.tecnica}
                onChange={(v) => atualizarDados((d) => ({ ...d, ficha: { ...d.ficha, tecnica: campoEditado(v) } }))}
              />
              <CampoTexto
                id="empresa"
                label="Empresa"
                campo={dados.ficha.empresa}
                onChange={(v) => atualizarDados((d) => ({ ...d, ficha: { ...d.ficha, empresa: campoEditado(v) } }))}
              />
              <CampoTexto
                id="data"
                label="Data"
                campo={dados.ficha.data}
                onChange={(v) => atualizarDados((d) => ({ ...d, ficha: { ...d.ficha, data: campoEditado(v) } }))}
              />
              <div className="sm:col-span-2">
                <CampoTexto
                  id="descricao"
                  label="Descrição"
                  campo={dados.ficha.descricao}
                  textarea
                  onChange={(v) => atualizarDados((d) => ({ ...d, ficha: { ...d.ficha, descricao: campoEditado(v) } }))}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Cores / Beneficiamentos</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Item</TableHead>
                    <TableHead>Descrição</TableHead>
                    <TableHead>Cor</TableHead>
                    <TableHead>Beneficiamento</TableHead>
                    <TableHead>Observações</TableHead>
                    <TableHead className="w-8" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dados.cores_beneficiamentos.map((linha, i) => (
                    <TableRow key={i}>
                      <TableCell>
                        <CelulaTexto
                          campo={linha.item}
                          onChange={(v) => atualizarDados((d) => atualizarItem(d, "cores_beneficiamentos", i, { item: campoEditado(v) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto
                          campo={linha.descricao}
                          onChange={(v) => atualizarDados((d) => atualizarItem(d, "cores_beneficiamentos", i, { descricao: campoEditado(v) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto
                          campo={linha.cor}
                          onChange={(v) => atualizarDados((d) => atualizarItem(d, "cores_beneficiamentos", i, { cor: campoEditado(v) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto
                          campo={linha.beneficiamento}
                          onChange={(v) => atualizarDados((d) => atualizarItem(d, "cores_beneficiamentos", i, { beneficiamento: campoEditado(v) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto
                          campo={linha.observacoes}
                          onChange={(v) => atualizarDados((d) => atualizarItem(d, "cores_beneficiamentos", i, { observacoes: campoEditado(v) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-muted-foreground hover:text-destructive"
                          aria-label="Remover linha"
                          onClick={() => atualizarDados((d) => removerItem(d, "cores_beneficiamentos", i))}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() =>
                  atualizarDados((d) => ({ ...d, cores_beneficiamentos: [...d.cores_beneficiamentos, corBeneficiamentoVazia()] }))
                }
              >
                <Plus className="h-3.5 w-3.5" />
                Adicionar linha
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ─── PÁGINA 2: GRADE, AVIAMENTOS, TECIDOS, CUSTOS ──────────────────────────────── */}
        <TabsContent value="materiais" className="space-y-6 pt-4">
          <Card>
            <CardHeader>
              <CardTitle>Grade de tamanhos</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="mb-2 text-sm font-medium text-foreground">Comerciais</p>
                <div className="flex flex-wrap gap-4">
                  {TAMANHOS_COMERCIAIS.map((tamanho) => (
                    <label key={tamanho} className="flex items-center gap-1.5 text-sm text-foreground">
                      <Checkbox
                        checked={dados.grade.comerciais.valor.includes(tamanho)}
                        onCheckedChange={() =>
                          atualizarDados((d) => ({
                            ...d,
                            grade: { ...d.grade, comerciais: campoEditado(alternarTamanho(d.grade.comerciais.valor, tamanho)) },
                          }))
                        }
                      />
                      {tamanho}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-2 text-sm font-medium text-foreground">Numéricos</p>
                <div className="flex flex-wrap gap-4">
                  {TAMANHOS_NUMERICOS.map((tamanho) => (
                    <label key={tamanho} className="flex items-center gap-1.5 text-sm text-foreground">
                      <Checkbox
                        checked={dados.grade.numericos.valor.includes(tamanho)}
                        onCheckedChange={() =>
                          atualizarDados((d) => ({
                            ...d,
                            grade: { ...d.grade, numericos: campoEditado(alternarTamanho(d.grade.numericos.valor, tamanho)) },
                          }))
                        }
                      />
                      {tamanho}
                    </label>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Aviamentos</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Descrição</TableHead>
                    <TableHead>Composição</TableHead>
                    <TableHead>Cor</TableHead>
                    <TableHead>Quantidade</TableHead>
                    <TableHead>Fornecedor</TableHead>
                    <TableHead>Preço</TableHead>
                    <TableHead className="w-8" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dados.aviamentos.map((linha, i) => (
                    <TableRow key={i}>
                      <TableCell>
                        <CelulaTexto campo={linha.descricao} onChange={(v) => atualizarDados((d) => atualizarItem(d, "aviamentos", i, { descricao: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto campo={linha.composicao} onChange={(v) => atualizarDados((d) => atualizarItem(d, "aviamentos", i, { composicao: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto campo={linha.cor} onChange={(v) => atualizarDados((d) => atualizarItem(d, "aviamentos", i, { cor: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaNumero campo={linha.quantidade} onChange={(v) => atualizarDados((d) => atualizarItem(d, "aviamentos", i, { quantidade: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto campo={linha.fornecedor} onChange={(v) => atualizarDados((d) => atualizarItem(d, "aviamentos", i, { fornecedor: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaNumero campo={linha.preco} onChange={(v) => atualizarDados((d) => atualizarItem(d, "aviamentos", i, { preco: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-muted-foreground hover:text-destructive"
                          aria-label="Remover linha"
                          onClick={() => atualizarDados((d) => removerItem(d, "aviamentos", i))}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => atualizarDados((d) => ({ ...d, aviamentos: [...d.aviamentos, aviamentoVazio()] }))}
              >
                <Plus className="h-3.5 w-3.5" />
                Adicionar linha
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Tecidos</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Descrição</TableHead>
                    <TableHead>Composição</TableHead>
                    <TableHead>Cor</TableHead>
                    <TableHead>Quantidade</TableHead>
                    <TableHead>Largura</TableHead>
                    <TableHead>Fornecedor</TableHead>
                    <TableHead>Preço</TableHead>
                    <TableHead className="w-8" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dados.tecidos.map((linha, i) => (
                    <TableRow key={i}>
                      <TableCell>
                        <CelulaTexto campo={linha.descricao} onChange={(v) => atualizarDados((d) => atualizarItem(d, "tecidos", i, { descricao: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto campo={linha.composicao} onChange={(v) => atualizarDados((d) => atualizarItem(d, "tecidos", i, { composicao: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto campo={linha.cor} onChange={(v) => atualizarDados((d) => atualizarItem(d, "tecidos", i, { cor: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaNumero campo={linha.quantidade} onChange={(v) => atualizarDados((d) => atualizarItem(d, "tecidos", i, { quantidade: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaNumero campo={linha.largura} onChange={(v) => atualizarDados((d) => atualizarItem(d, "tecidos", i, { largura: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto campo={linha.fornecedor} onChange={(v) => atualizarDados((d) => atualizarItem(d, "tecidos", i, { fornecedor: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <CelulaNumero campo={linha.preco} onChange={(v) => atualizarDados((d) => atualizarItem(d, "tecidos", i, { preco: campoEditado(v) }))} />
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-muted-foreground hover:text-destructive"
                          aria-label="Remover linha"
                          onClick={() => atualizarDados((d) => removerItem(d, "tecidos", i))}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => atualizarDados((d) => ({ ...d, tecidos: [...d.tecidos, tecidoVazio()] }))}
              >
                <Plus className="h-3.5 w-3.5" />
                Adicionar linha
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Custos</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {(
                [
                  ["aviamentos", "Aviamentos"],
                  ["tecidos", "Tecidos"],
                  ["costura_beneficiamento", "Costura/Beneficiamento"],
                  ["outros", "Outros"],
                  ["preco_total", "Preço total"],
                ] as const
              ).map(([chave, rotulo]) => (
                <div key={chave} className="space-y-2 rounded-lg border border-border p-3">
                  <p className="text-sm font-medium text-foreground">{rotulo}</p>
                  <CampoNumero
                    id={`custo-${chave}`}
                    label="Valor (R$)"
                    campo={dados.custos[chave].custo}
                    onChange={(v) =>
                      atualizarDados((d) => ({
                        ...d,
                        custos: { ...d.custos, [chave]: { ...d.custos[chave], custo: campoEditado(v) } },
                      }))
                    }
                  />
                  <CampoTexto
                    id={`obs-${chave}`}
                    label="Observação"
                    campo={dados.custos[chave].observacao}
                    onChange={(v) =>
                      atualizarDados((d) => ({
                        ...d,
                        custos: { ...d.custos, [chave]: { ...d.custos[chave], observacao: campoEditado(v) } },
                      }))
                    }
                  />
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ─── PÁGINA 3: SEQUÊNCIA OPERACIONAL + MODELAGEM ───────────────────────────────── */}
        <TabsContent value="producao" className="space-y-6 pt-4">
          <Card>
            <CardHeader>
              <CardTitle>Sequência operacional</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">Etapa</TableHead>
                    <TableHead>Descrição da operação</TableHead>
                    <TableHead>Máquina(s)</TableHead>
                    <TableHead className="w-8" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dados.sequencia_operacional.map((linha, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-sm text-muted-foreground">{i + 1}</TableCell>
                      <TableCell>
                        <CelulaTexto
                          campo={linha.descricao}
                          onChange={(v) => atualizarDados((d) => atualizarItem(d, "sequencia_operacional", i, { descricao: campoEditado(v) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <CelulaTexto
                          campo={linha.maquinas}
                          onChange={(v) => atualizarDados((d) => atualizarItem(d, "sequencia_operacional", i, { maquinas: campoEditado(v) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-muted-foreground hover:text-destructive"
                          aria-label="Remover linha"
                          onClick={() => atualizarDados((d) => removerItem(d, "sequencia_operacional", i))}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => atualizarDados((d) => ({ ...d, sequencia_operacional: [...d.sequencia_operacional, operacaoVazia()] }))}
              >
                <Plus className="h-3.5 w-3.5" />
                Adicionar etapa
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Modelagem</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <CampoTexto
                  id="modelista"
                  label="Modelista"
                  campo={dados.modelagem.modelista}
                  onChange={(v) => atualizarDados((d) => ({ ...d, modelagem: { ...d.modelagem, modelista: campoEditado(v) } }))}
                />
                <CampoNumero
                  id="numero_moldes"
                  label="Quantidade de moldes"
                  campo={dados.modelagem.numero_moldes}
                  onChange={(v) => atualizarDados((d) => ({ ...d, modelagem: { ...d.modelagem, numero_moldes: campoEditado(v) } }))}
                />
              </div>

              <div>
                <p className="mb-2 text-sm font-medium text-foreground">Partes / componentes da modelagem</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Parte</TableHead>
                      <TableHead>Observações</TableHead>
                      <TableHead className="w-8" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {dados.modelagem.partes.map((linha, i) => (
                      <TableRow key={i}>
                        <TableCell>
                          <CelulaTexto
                            campo={linha.descricao}
                            onChange={(v) =>
                              atualizarDados((d) => ({
                                ...d,
                                modelagem: { ...d.modelagem, partes: atualizarItemLista(d.modelagem.partes, i, { descricao: campoEditado(v) }) },
                              }))
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <CelulaTexto
                            campo={linha.observacoes}
                            onChange={(v) =>
                              atualizarDados((d) => ({
                                ...d,
                                modelagem: { ...d.modelagem, partes: atualizarItemLista(d.modelagem.partes, i, { observacoes: campoEditado(v) }) },
                              }))
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="text-muted-foreground hover:text-destructive"
                            aria-label="Remover linha"
                            onClick={() =>
                              atualizarDados((d) => ({
                                ...d,
                                modelagem: { ...d.modelagem, partes: d.modelagem.partes.filter((_, idx) => idx !== i) },
                              }))
                            }
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() =>
                    atualizarDados((d) => ({ ...d, modelagem: { ...d.modelagem, partes: [...d.modelagem.partes, parteModelagemVazia()] } }))
                  }
                >
                  <Plus className="h-3.5 w-3.5" />
                  Adicionar parte
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ─── Helpers de atualização imutável das listas dinâmicas ──────────────────────────────────────

function alternarTamanho(atual: string[], tamanho: string): string[] {
  return atual.includes(tamanho) ? atual.filter((t) => t !== tamanho) : [...atual, tamanho];
}

function atualizarItemLista<T>(lista: T[], indice: number, atualizacao: Partial<T>): T[] {
  return lista.map((item, i) => (i === indice ? { ...item, ...atualizacao } : item));
}

// Chaves de Ficha["dados"] que são listas de itens editáveis por linha -- usado por atualizarItem/
// removerItem abaixo para não repetir a mesma função 4 vezes (cores_beneficiamentos, aviamentos,
// tecidos, sequencia_operacional). "modelagem.partes" fica de fora por estar aninhada um nível
// mais fundo (dentro de "modelagem"), tratada inline nos handlers acima.
type ListasEditaveis = {
  cores_beneficiamentos: CorBeneficiamento;
  aviamentos: Aviamento;
  tecidos: Tecido;
  sequencia_operacional: Operacao;
};

function atualizarItem<K extends keyof ListasEditaveis>(
  dados: DadosFicha,
  chave: K,
  indice: number,
  atualizacao: Partial<ListasEditaveis[K]>
): DadosFicha {
  // TypeScript não estreita `dados[chave]` para o array específico de K a partir de um genérico
  // indexado assim -- a asserção é segura porque K vem de keyof ListasEditaveis, então
  // dados[chave] é sempre um array de ListasEditaveis[K] em tempo de execução.
  const lista = dados[chave] as ListasEditaveis[K][];
  return { ...dados, [chave]: atualizarItemLista(lista, indice, atualizacao) };
}

function removerItem<K extends keyof ListasEditaveis>(dados: DadosFicha, chave: K, indice: number): DadosFicha {
  const lista = dados[chave] as ListasEditaveis[K][];
  return { ...dados, [chave]: lista.filter((_, i) => i !== indice) };
}
