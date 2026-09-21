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
  DesenhoFicha,
  Ficha,
  Operacao,
  Tecido,
  aprovarDesenho,
  aviamentoVazio,
  atualizarFicha,
  baixarFichaDocumento,
  campoEditado,
  corBeneficiamentoVazia,
  gerarDesenho,
  importarCroquiComoDesenho,
  obterFicha,
  operacaoVazia,
  parteModelagemVazia,
  tecidoVazio,
  urlDesenho,
  urlPreviewFicha,
} from "@/lib/api";
import { ROTULO_STATUS_FICHA, VARIANTE_STATUS_FICHA } from "@/lib/fichas-status";
import { mensagemAmigavel } from "@/lib/erros";
import ImportarCroquiDialog from "@/components/ImportarCroquiDialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import OrigemIndicador from "@/components/fichas/OrigemIndicador";
import { AlertTriangle, ArrowLeft, FileDown, ImagePlus, Images, Loader2, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
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
  // Guarda qual formato está sendo gerado (não só "gerando: sim/não"), para o spinner aparecer
  // no botão certo quando há dois.
  const [gerando, setGerando] = useState<"docx" | "pdf" | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [gerandoPreview, setGerandoPreview] = useState(false);
  const [erroPreview, setErroPreview] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [gerandoDesenho, setGerandoDesenho] = useState(false);
  const [instrucaoAdicional, setInstrucaoAdicional] = useState("");
  const [dialogoImportarCroquiAberto, setDialogoImportarCroquiAberto] = useState(false);
  const [importandoCroqui, setImportandoCroqui] = useState(false);

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
        const msg = mensagemAmigavel(e, "Não foi possível carregar a ficha.");
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

  // Mesma ideia, para o campo irmão "desenho" (fora de "dados") -- hoje só o checkbox
  // "solicitado" é editado diretamente aqui; versões/aprovação passam pelas funções abaixo, que
  // chamam o backend em vez de só alterar o estado local.
  function atualizarDesenho(atualizar: (desenho: DesenhoFicha) => DesenhoFicha) {
    setFicha((atual) => (atual ? { ...atual, desenho: atualizar(atual.desenho) } : atual));
  }

  async function gerarOuRegenerarDesenho() {
    if (!ficha) return;
    setGerandoDesenho(true);
    try {
      // Salva antes de gerar, mesmo motivo do Word/PDF/prévia: o backend monta o prompt a partir
      // dos dados que estão em disco, então uma edição não salva (ex: descrição da peça) ficaria
      // de fora do desenho sem o usuário perceber.
      const salva = await atualizarFicha(TENANT_ID, ficha, ficha.atualizado_em);
      setFicha(salva.ficha);
      setAlertas(salva.alertas);

      const resultado = await gerarDesenho(TENANT_ID, salva.ficha.id, instrucaoAdicional || undefined);
      setFicha(resultado.ficha);
      setAlertas(resultado.alertas);
      setInstrucaoAdicional("");
      toast.success("Desenho técnico gerado.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) {
        toast.error("Esta ficha foi alterada em outra sessão/aba. Recarregue a página antes de gerar o desenho.");
      } else if (e instanceof ApiError && (e.status === 422 || e.status === 429)) {
        // 422 = moderação reprovou o prompt; 429 = cota diária de imagens atingida. Nos dois
        // casos a mensagem do backend já é a que deve chegar ao usuário, sem reformular.
        toast.error(e.message);
      } else {
        toast.error(mensagemAmigavel(e, "Não foi possível gerar o desenho técnico."));
      }
    } finally {
      setGerandoDesenho(false);
    }
  }

  async function aprovarVersaoDesenho(versao: number) {
    if (!ficha) return;
    try {
      const resultado = await aprovarDesenho(TENANT_ID, ficha.id, versao);
      setFicha(resultado.ficha);
      setAlertas(resultado.alertas);
      toast.success(`Versão ${versao} aprovada.`);
    } catch (e) {
      toast.error(mensagemAmigavel(e, "Não foi possível aprovar a versão."));
    }
  }

  async function importarCroqui(croquiId: string) {
    if (!ficha) return;
    setImportandoCroqui(true);
    try {
      const resultado = await importarCroquiComoDesenho(TENANT_ID, ficha.id, croquiId);
      setFicha(resultado.ficha);
      setAlertas(resultado.alertas);
      setDialogoImportarCroquiAberto(false);
      toast.success("Croqui importado como desenho técnico.");
    } catch (e) {
      toast.error(mensagemAmigavel(e, "Não foi possível importar o croqui."));
    } finally {
      setImportandoCroqui(false);
    }
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
        toast.error(mensagemAmigavel(e, "Não foi possível salvar a ficha."));
      }
    } finally {
      setSalvando(false);
    }
  }

  async function gerarDocumento(formato: "docx" | "pdf") {
    if (!ficha) return;
    setGerando(formato);
    try {
      // Salva antes de gerar: o backend renderiza a partir do que está em disco, então edições
      // não salvas sairiam de fora do documento sem o usuário perceber.
      const salva = await atualizarFicha(TENANT_ID, ficha, ficha.atualizado_em);
      setFicha(salva.ficha);
      setAlertas(salva.alertas);

      await baixarFichaDocumento(TENANT_ID, ficha.id, formato);
      toast.success(formato === "pdf" ? "PDF gerado." : "Documento Word gerado.");

      // O backend muda o status para "Documento gerado" ao renderizar -- recarrega para a tela
      // refletir isso sem precisar de F5.
      const atualizada = await obterFicha(TENANT_ID, ficha.id);
      setFicha(atualizada.ficha);
      setAlertas(atualizada.alertas);
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) {
        toast.error("Esta ficha foi alterada em outra sessão/aba. Recarregue a página antes de gerar o documento.");
      } else {
        // 501 = LibreOffice ausente no servidor -- a mensagem crua do backend fala em variável de
        // ambiente e caminho de executável (jargão de infraestrutura); mensagemAmigavel() já
        // traduz isso para algo que faz sentido pra quem não instalou nada (Fase 14, Bloco U).
        toast.error(mensagemAmigavel(e, "Não foi possível gerar o documento."));
      }
    } finally {
      setGerando(null);
    }
  }

  async function atualizarPreview() {
    if (!ficha) return;
    setGerandoPreview(true);
    setErroPreview(null);
    try {
      // Salva antes de gerar, pelo mesmo motivo do Word/PDF: a prévia vem do que está em disco,
      // então uma edição não salva ficaria de fora dela sem o usuário perceber.
      const salva = await atualizarFicha(TENANT_ID, ficha, ficha.atualizado_em);
      setFicha(salva.ficha);
      setAlertas(salva.alertas);

      // Cache-buster: sem isso, o navegador poderia reaproveitar o PDF antigo da mesma URL em
      // vez de buscar a versão recém-atualizada.
      setPreviewUrl(`${urlPreviewFicha(TENANT_ID, ficha.id)}&_=${Date.now()}`);
    } catch (e) {
      const msg =
        e instanceof ApiError && e.status === 412
          ? "Esta ficha foi alterada em outra sessão/aba. Recarregue a página antes de atualizar a prévia."
          : mensagemAmigavel(e, "Não foi possível gerar a pré-visualização.");
      setErroPreview(msg);
      toast.error(msg);
    } finally {
      setGerandoPreview(false);
    }
  }

  if (carregando) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-6 p-6">
        <div className="flex items-center justify-between gap-3">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-9 w-28" />
        </div>
        <Skeleton className="h-8 w-64 max-w-full" />
        <div className="flex gap-2">
          <Skeleton className="h-8 w-28" />
          <Skeleton className="h-8 w-28" />
          <Skeleton className="h-8 w-28" />
          <Skeleton className="h-8 w-28" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
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
    <>
    <div className="mx-auto w-full max-w-4xl space-y-6 p-6">
      <div className="flex items-center justify-between gap-3">
        <Link href="/fichas" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          Voltar às fichas
        </Link>
        <div className="flex items-center gap-2">
          <Badge variant={VARIANTE_STATUS_FICHA[ficha.status]}>{ROTULO_STATUS_FICHA[ficha.status]}</Badge>
          <Button onClick={salvar} disabled={salvando || gerando !== null} variant="outline">
            {salvando ? <Loader2 className="animate-spin" /> : <Save />}
            {salvando ? "Salvando..." : "Salvar"}
          </Button>
          <Button onClick={() => gerarDocumento("docx")} disabled={salvando || gerando !== null} variant="outline">
            {gerando === "docx" ? <Loader2 className="animate-spin" /> : <FileDown />}
            {gerando === "docx" ? "Gerando..." : "Word"}
          </Button>
          <Button onClick={() => gerarDocumento("pdf")} disabled={salvando || gerando !== null}>
            {gerando === "pdf" ? <Loader2 className="animate-spin" /> : <FileDown />}
            {gerando === "pdf" ? "Gerando..." : "PDF"}
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

      <Tabs
        defaultValue="identificacao"
        onValueChange={(valor) => {
          // Carrega a prévia só na primeira vez que a aba é aberta -- gerar o PDF tem custo real
          // (conversão via LibreOffice), então não faz sentido rodar isso a cada troca de aba.
          if (valor === "previsualizacao" && !previewUrl && !gerandoPreview) {
            atualizarPreview();
          }
        }}
      >
        <TabsList>
          <TabsTrigger value="identificacao">1. Identificação</TabsTrigger>
          <TabsTrigger value="materiais">2. Tamanhos e Custos</TabsTrigger>
          <TabsTrigger value="producao">3. Produção</TabsTrigger>
          <TabsTrigger value="previsualizacao">Pré-visualização</TabsTrigger>
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
              <CardTitle>Desenho técnico (opcional)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <label className="flex items-center gap-2 text-sm text-foreground">
                <Checkbox
                  checked={ficha.desenho.solicitado}
                  onCheckedChange={(v) => atualizarDesenho((d) => ({ ...d, solicitado: v === true }))}
                />
                Solicitar desenho técnico para esta ficha
              </label>

              {ficha.desenho.solicitado && (
                <div className="space-y-4">
                  {ficha.desenho.versoes.length === 0 ? (
                    <div className="flex flex-wrap gap-2">
                      <Button onClick={gerarOuRegenerarDesenho} disabled={gerandoDesenho} variant="outline" size="sm">
                        {gerandoDesenho ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImagePlus className="h-3.5 w-3.5" />}
                        {gerandoDesenho ? "Gerando..." : "Gerar desenho técnico"}
                      </Button>
                      <Button onClick={() => setDialogoImportarCroquiAberto(true)} variant="outline" size="sm">
                        <Images className="h-3.5 w-3.5" />
                        Importar da galeria de croquis
                      </Button>
                    </div>
                  ) : (
                    <>
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {[...ficha.desenho.versoes].reverse().map((v) => (
                          <div key={v.versao} className="space-y-2 rounded-lg border border-border p-3">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-sm font-medium text-foreground">Versão {v.versao}</span>
                              <Badge variant={v.status === "aprovado" ? "default" : "outline"}>
                                {v.status === "aprovado" ? "Aprovado" : "Aguardando aprovação"}
                              </Badge>
                            </div>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={urlDesenho(TENANT_ID, ficha.id, v.versao)}
                              alt={`Desenho técnico, versão ${v.versao}`}
                              className="w-full rounded border border-border"
                            />
                            {v.status !== "aprovado" && (
                              <Button
                                onClick={() => aprovarVersaoDesenho(v.versao)}
                                variant="outline"
                                size="sm"
                                className="w-full"
                              >
                                Aprovar esta versão
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>

                      <div className="space-y-2 rounded-lg border border-dashed border-border p-3">
                        <p className="text-xs text-muted-foreground">
                          gpt-image-1 não tem controle de repetição exata: cada regeneração cria uma
                          peça nova a partir do ajuste pedido, não uma correção pontual da versão
                          anterior.
                        </p>
                        <Textarea
                          placeholder="Ex.: a manga é 3/4, não curta"
                          value={instrucaoAdicional}
                          onChange={(e) => setInstrucaoAdicional(e.target.value)}
                          rows={2}
                        />
                        <div className="flex flex-wrap gap-2">
                          <Button onClick={gerarOuRegenerarDesenho} disabled={gerandoDesenho} variant="outline" size="sm">
                            {gerandoDesenho ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                            {gerandoDesenho ? "Gerando..." : "Gerar nova versão"}
                          </Button>
                          <Button onClick={() => setDialogoImportarCroquiAberto(true)} variant="outline" size="sm">
                            <Images className="h-3.5 w-3.5" />
                            Importar da galeria
                          </Button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}
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

        {/* ─── PRÉ-VISUALIZAÇÃO: PDF real, gerado pelo mesmo pipeline do "Gerar PDF" ────── */}
        <TabsContent value="previsualizacao" className="pt-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>Pré-visualização</CardTitle>
                <Button onClick={atualizarPreview} disabled={gerandoPreview} variant="outline" size="sm">
                  {gerandoPreview ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                  {gerandoPreview ? "Atualizando..." : "Atualizar prévia"}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {gerandoPreview && !previewUrl ? (
                <div className="flex flex-col items-center gap-2 py-16 text-center">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Gerando pré-visualização...</p>
                </div>
              ) : erroPreview && !previewUrl ? (
                <div className="flex flex-col items-center gap-2 py-16 text-center">
                  <AlertTriangle className="h-6 w-6 text-destructive" />
                  <p className="max-w-md text-sm text-muted-foreground">{erroPreview}</p>
                </div>
              ) : previewUrl ? (
                <iframe
                  src={previewUrl}
                  title="Pré-visualização da ficha técnica"
                  className="h-[70vh] w-full rounded-lg border border-border"
                />
              ) : (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Clique em &quot;Atualizar prévia&quot; para ver como a ficha fica no documento final.
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
    <ImportarCroquiDialog
      open={dialogoImportarCroquiAberto}
      onOpenChange={setDialogoImportarCroquiAberto}
      tenantId={TENANT_ID}
      importando={importandoCroqui}
      onImportar={importarCroqui}
    />
    </>
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
