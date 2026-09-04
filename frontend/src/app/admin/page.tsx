"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  TenantConfig,
  adminLogin,
  deletarDocumento,
  listarDocumentos,
  obterConfigTenant,
  uploadDocumento,
} from "@/lib/api";

const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";
const CHAVE_SESSAO_ADMIN = "labfashion_admin_ok";

export default function AdminPage() {
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [autorizado, setAutorizado] = useState(false);
  const [senha, setSenha] = useState("");
  const [erroLogin, setErroLogin] = useState<string | null>(null);
  const [validandoLogin, setValidandoLogin] = useState(false);

  const [documentos, setDocumentos] = useState<string[]>([]);
  const [carregandoDocs, setCarregandoDocs] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagemSucesso, setMensagemSucesso] = useState<string | null>(null);
  const inputArquivoRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    obterConfigTenant(TENANT_ID)
      .then(setConfig)
      .catch(() => setConfig(null));

    if (typeof window !== "undefined" && window.sessionStorage.getItem(CHAVE_SESSAO_ADMIN) === "1") {
      setAutorizado(true);
    }
  }, []);

  useEffect(() => {
    if (autorizado) {
      recarregarDocumentos();
    }
  }, [autorizado]);

  async function recarregarDocumentos() {
    setCarregandoDocs(true);
    try {
      const lista = await listarDocumentos(TENANT_ID);
      setDocumentos(lista);
    } catch {
      setErro("Não foi possível carregar a lista de documentos.");
    } finally {
      setCarregandoDocs(false);
    }
  }

  async function fazerLogin(e: React.FormEvent) {
    e.preventDefault();
    setValidandoLogin(true);
    setErroLogin(null);
    try {
      const ok = await adminLogin(TENANT_ID, senha);
      if (ok) {
        setAutorizado(true);
        window.sessionStorage.setItem(CHAVE_SESSAO_ADMIN, "1");
      } else {
        setErroLogin("Senha incorreta.");
      }
    } catch (e) {
      setErroLogin(e instanceof ApiError ? e.message : "Falha ao conectar com a API.");
    } finally {
      setValidandoLogin(false);
    }
  }

  async function enviarArquivo() {
    const arquivo = inputArquivoRef.current?.files?.[0];
    if (!arquivo) return;

    setEnviando(true);
    setErro(null);
    setMensagemSucesso(null);
    try {
      const resultado = await uploadDocumento(TENANT_ID, arquivo);
      setMensagemSucesso(`"${resultado.nome_arquivo}" indexado com sucesso (${resultado.chunks_indexados} trechos).`);
      if (inputArquivoRef.current) inputArquivoRef.current.value = "";
      await recarregarDocumentos();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao enviar o arquivo.");
    } finally {
      setEnviando(false);
    }
  }

  async function excluirDocumento(nome: string) {
    if (!window.confirm(`Remover "${nome}" da Base de Conhecimento?`)) return;
    setErro(null);
    try {
      await deletarDocumento(TENANT_ID, nome);
      await recarregarDocumentos();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao remover o documento.");
    }
  }

  const corPrimaria = config?.cor_primaria ?? "#0047AB";

  if (!autorizado) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <form
          onSubmit={fazerLogin}
          className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 w-full max-w-sm space-y-4"
        >
          <h1 className="text-lg font-semibold text-gray-900">Acesso administrativo</h1>
          <p className="text-sm text-gray-500">Informe a senha de administrador para gerenciar a Base de Conhecimento.</p>
          <input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            placeholder="Senha"
            autoFocus
            className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {erroLogin && <p className="text-sm text-red-600">{erroLogin}</p>}
          <button
            type="submit"
            disabled={validandoLogin || !senha}
            className="w-full rounded-lg text-white font-medium py-2 disabled:opacity-40"
            style={{ backgroundColor: corPrimaria }}
          >
            {validandoLogin ? "Validando..." : "Entrar"}
          </button>
          <Link href="/" className="block text-center text-sm text-gray-400 hover:text-gray-600">
            ← Voltar ao chat
          </Link>
        </form>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Base de Conhecimento — {config?.nome ?? TENANT_ID}</h1>
        <Link href="/" className="text-sm text-gray-500 hover:text-gray-800">
          ← Voltar ao chat
        </Link>
      </div>

      <section className="bg-white rounded-2xl border border-gray-200 p-4 space-y-3">
        <h2 className="font-medium text-gray-800">Indexar novo documento</h2>
        <p className="text-xs text-gray-500">Formatos aceitos: PDF, Word, TXT, Markdown, CSV, Excel, PowerPoint.</p>
        <div className="flex gap-2">
          <input ref={inputArquivoRef} type="file" className="flex-1 text-sm" />
          <button
            onClick={enviarArquivo}
            disabled={enviando}
            className="rounded-lg px-4 py-2 text-white text-sm font-medium disabled:opacity-40"
            style={{ backgroundColor: corPrimaria }}
          >
            {enviando ? "Enviando..." : "📥 Indexar"}
          </button>
        </div>
        {mensagemSucesso && <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">{mensagemSucesso}</p>}
        {erro && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{erro}</p>}
      </section>

      <section className="bg-white rounded-2xl border border-gray-200 p-4 space-y-2">
        <h2 className="font-medium text-gray-800">Documentos indexados ({documentos.length})</h2>
        {carregandoDocs ? (
          <p className="text-sm text-gray-400">Carregando...</p>
        ) : documentos.length === 0 ? (
          <p className="text-sm text-gray-400">Nenhum documento indexado ainda.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {documentos.map((doc) => (
              <li key={doc} className="flex items-center justify-between py-2 text-sm">
                <span className="text-gray-700 truncate">📄 {doc}</span>
                <button
                  onClick={() => excluirDocumento(doc)}
                  className="text-gray-400 hover:text-red-600 shrink-0 ml-2"
                  title="Remover"
                >
                  🗑️
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
