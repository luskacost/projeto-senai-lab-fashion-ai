"use client";

import { useEffect, useState } from "react";
import { AparenciaTenant, ApiError, TenantConfig, atualizarConfigTenant } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

const OPCOES_FONTE = ["Inter", "Roboto", "Poppins"];

interface Props {
  tenantId: string;
  config: TenantConfig | null;
  corPrimaria: string;
  onSalvo: () => void;
}

function valoresIniciais(config: TenantConfig | null): AparenciaTenant {
  return {
    nome: (config?.nome as string) ?? "",
    cor_primaria: (config?.cor_primaria as string) ?? "#0047AB",
    cor_secundaria: (config?.cor_secundaria as string) ?? "#F47B20",
    logo_url: (config?.logo_url as string) ?? "",
    tema: (config?.tema as "claro" | "escuro") ?? "claro",
    fonte: (config?.fonte as string) ?? "Inter",
    favicon_url: (config?.favicon_url as string) ?? "",
    mensagem_boas_vindas: (config?.mensagem_boas_vindas as string) ?? "",
  };
}

export default function AparenciaForm({ tenantId, config, corPrimaria, onSalvo }: Props) {
  const [form, setForm] = useState<AparenciaTenant>(valoresIniciais(config));
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    setForm(valoresIniciais(config));
  }, [config]);

  function atualizarCampo<K extends keyof AparenciaTenant>(campo: K, valor: AparenciaTenant[K]) {
    setForm((atual) => ({ ...atual, [campo]: valor }));
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    try {
      await atualizarConfigTenant(tenantId, { ...form, nome: form.nome.trim(), logo_url: form.logo_url.trim(), favicon_url: form.favicon_url.trim() });
      toast.success("Configurações salvas com sucesso!");
      onSalvo();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Falha ao salvar as configurações.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Aparência</CardTitle>
        <CardDescription>
          Personaliza nome, cores, tema, fonte, logo e mensagem de boas-vindas exibidos no chat.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={salvar} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="nome">Nome da aplicação</Label>
            <Input id="nome" value={form.nome} onChange={(e) => atualizarCampo("nome", e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="cor_primaria">Cor primária</Label>
              <input
                id="cor_primaria"
                type="color"
                value={form.cor_primaria}
                onChange={(e) => atualizarCampo("cor_primaria", e.target.value)}
                className="h-9 w-full cursor-pointer rounded-lg border border-input bg-transparent"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cor_secundaria">Cor secundária</Label>
              <input
                id="cor_secundaria"
                type="color"
                value={form.cor_secundaria}
                onChange={(e) => atualizarCampo("cor_secundaria", e.target.value)}
                className="h-9 w-full cursor-pointer rounded-lg border border-input bg-transparent"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Tema</Label>
              <ToggleGroup
                value={[form.tema]}
                onValueChange={(valores) => valores.length > 0 && atualizarCampo("tema", valores[0] as "claro" | "escuro")}
                variant="outline"
                size="sm"
              >
                <ToggleGroupItem value="claro">☀️ Claro</ToggleGroupItem>
                <ToggleGroupItem value="escuro">🌙 Escuro</ToggleGroupItem>
              </ToggleGroup>
            </div>
            <div className="space-y-1.5">
              <Label>Tipografia</Label>
              <Select value={form.fonte} onValueChange={(valor) => atualizarCampo("fonte", valor as string)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OPCOES_FONTE.map((f) => (
                    <SelectItem key={f} value={f}>
                      {f}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="logo_url">URL do logo (opcional)</Label>
            <Input
              id="logo_url"
              value={form.logo_url}
              onChange={(e) => atualizarCampo("logo_url", e.target.value)}
              placeholder="Deixe em branco para usar o logo padrão"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="favicon_url">URL do favicon (opcional)</Label>
            <Input
              id="favicon_url"
              value={form.favicon_url}
              onChange={(e) => atualizarCampo("favicon_url", e.target.value)}
              placeholder="Deixe em branco para usar o emoji padrão"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="mensagem_boas_vindas">Mensagem de boas-vindas</Label>
            <Textarea
              id="mensagem_boas_vindas"
              value={form.mensagem_boas_vindas}
              onChange={(e) => atualizarCampo("mensagem_boas_vindas", e.target.value)}
              rows={3}
            />
          </div>

          <Button type="submit" disabled={salvando} className="text-white" style={{ backgroundColor: corPrimaria }}>
            {salvando && <Loader2 className="animate-spin" />}
            {salvando ? "Salvando..." : "Salvar alterações"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
