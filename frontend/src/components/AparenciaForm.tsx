"use client";

import { useEffect, useState } from "react";
import { AparenciaTenant, ApiError, TenantConfig, atualizarConfigTenant } from "@/lib/api";

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
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState(false);

  useEffect(() => {
    setForm(valoresIniciais(config));
  }, [config]);

  function atualizarCampo<K extends keyof AparenciaTenant>(campo: K, valor: AparenciaTenant[K]) {
    setForm((atual) => ({ ...atual, [campo]: valor }));
    setSucesso(false);
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro(null);
    setSucesso(false);
    try {
      await atualizarConfigTenant(tenantId, { ...form, nome: form.nome.trim(), logo_url: form.logo_url.trim(), favicon_url: form.favicon_url.trim() });
      setSucesso(true);
      onSalvo();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao salvar as configurações.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <form onSubmit={salvar} className="bg-white rounded-2xl border border-gray-200 p-4 space-y-4">
      <h2 className="font-medium text-gray-800">Aparência</h2>
      <p className="text-xs text-gray-500">
        Personaliza nome, cores, tema, fonte, logo e mensagem de boas-vindas exibidos no chat.
      </p>

      <div>
        <label className="block text-sm text-gray-600 mb-1">Nome da aplicação</label>
        <input
          value={form.nome}
          onChange={(e) => atualizarCampo("nome", e.target.value)}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-600 mb-1">Cor primária</label>
          <input
            type="color"
            value={form.cor_primaria}
            onChange={(e) => atualizarCampo("cor_primaria", e.target.value)}
            className="w-full h-10 rounded-lg border border-gray-300 cursor-pointer"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Cor secundária</label>
          <input
            type="color"
            value={form.cor_secundaria}
            onChange={(e) => atualizarCampo("cor_secundaria", e.target.value)}
            className="w-full h-10 rounded-lg border border-gray-300 cursor-pointer"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-600 mb-1">Tema</label>
          <div className="flex gap-3 text-sm">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={form.tema === "claro"}
                onChange={() => atualizarCampo("tema", "claro")}
              />
              ☀️ Claro
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={form.tema === "escuro"}
                onChange={() => atualizarCampo("tema", "escuro")}
              />
              🌙 Escuro
            </label>
          </div>
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Tipografia</label>
          <select
            value={form.fonte}
            onChange={(e) => atualizarCampo("fonte", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            {OPCOES_FONTE.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="block text-sm text-gray-600 mb-1">URL do logo (opcional)</label>
        <input
          value={form.logo_url}
          onChange={(e) => atualizarCampo("logo_url", e.target.value)}
          placeholder="Deixe em branco para usar o logo padrão"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div>
        <label className="block text-sm text-gray-600 mb-1">URL do favicon (opcional)</label>
        <input
          value={form.favicon_url}
          onChange={(e) => atualizarCampo("favicon_url", e.target.value)}
          placeholder="Deixe em branco para usar o emoji padrão"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div>
        <label className="block text-sm text-gray-600 mb-1">Mensagem de boas-vindas</label>
        <textarea
          value={form.mensagem_boas_vindas}
          onChange={(e) => atualizarCampo("mensagem_boas_vindas", e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {sucesso && (
        <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
          Configurações salvas com sucesso!
        </p>
      )}
      {erro && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{erro}</p>}

      <button
        type="submit"
        disabled={salvando}
        className="rounded-lg px-4 py-2 text-white text-sm font-medium disabled:opacity-40"
        style={{ backgroundColor: corPrimaria }}
      >
        {salvando ? "Salvando..." : "Salvar alterações"}
      </button>
    </form>
  );
}
