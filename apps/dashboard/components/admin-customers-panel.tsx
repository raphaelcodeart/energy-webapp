"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { CustomerRead } from "@/lib/types";

async function fetchCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

const KIND_LABELS: Record<string, string> = {
  PRIVATE: "Privato",
  SOLE_PROPRIETOR: "Partita IVA",
  COMPANY: "Azienda",
  CONDOMINIUM: "Condominio",
};

const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

export function AdminCustomersPanel() {
  const queryClient = useQueryClient();
  const { data: customers, error: loadError } = useQuery({
    queryKey: ["admin", "customers"],
    queryFn: fetchCustomers,
  });
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");

  // Create form state
  const [kind, setKind] = useState("PRIVATE");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [fiscalCode, setFiscalCode] = useState("");
  const [vatNumber, setVatNumber] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/customers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          email,
          phone: phone || null,
          fiscal_code: fiscalCode || null,
          vat_number: vatNumber || null,
          first_name: PRIVATE_LIKE.has(kind) ? firstName : null,
          last_name: PRIVATE_LIKE.has(kind) ? lastName : null,
          company_name: PRIVATE_LIKE.has(kind) ? null : companyName,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setShowCreate(false);
      setEmail("");
      setPhone("");
      setFirstName("");
      setLastName("");
      setCompanyName("");
      setFiscalCode("");
      setVatNumber("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il cliente.");
    } finally {
      setCreateLoading(false);
    }
  }

  const filtered = (customers ?? []).filter(
    (c) =>
      c.display_name.toLowerCase().includes(search.toLowerCase()) ||
      c.email.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="w-full sm:max-w-xs relative">
          <input
            type="text"
            placeholder="Cerca cliente..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl glass-input pl-10 pr-4 py-2 text-xs focus:border-violet-500"
          />
          <svg className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-500/20 transition cursor-pointer shrink-0"
        >
          + Nuovo Cliente
        </button>
      </div>

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare i clienti.</p>}

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-3 px-6">Nominativo</th>
                <th className="py-3 px-6">Tipo</th>
                <th className="py-3 px-6">Email</th>
                <th className="py-3 px-6">Telefono</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {customers === undefined ? (
                <tr>
                  <td colSpan={4} className="text-center py-8 text-slate-500">Caricamento...</td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={4} className="text-center py-8 text-slate-500">Nessun cliente trovato.</td>
                </tr>
              ) : (
                filtered.map((c) => (
                  <tr key={c.id} className="text-slate-300 light:text-slate-600 hover:bg-white/5 transition-colors">
                    <td className="py-4 px-6 font-medium text-white light:text-slate-900">{c.display_name}</td>
                    <td className="py-4 px-6">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-cyan-500/10 text-cyan-400 border-cyan-500/20">
                        {KIND_LABELS[c.kind] ?? c.kind}
                      </span>
                    </td>
                    <td className="py-4 px-6">{c.email}</td>
                    <td className="py-4 px-6">{c.phone ?? "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Nuovo Cliente</h3>
              <button
                onClick={() => setShowCreate(false)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo cliente</label>
                <select
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-violet-500"
                >
                  {Object.entries(KIND_LABELS).map(([code, label]) => (
                    <option key={code} value={code}>{label}</option>
                  ))}
                </select>
              </div>

              {PRIVATE_LIKE.has(kind) ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
                    <input required value={firstName} onChange={(e) => setFirstName(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cognome</label>
                    <input required value={lastName} onChange={(e) => setLastName(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Ragione sociale</label>
                  <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Email</label>
                  <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Telefono</label>
                  <input value={phone} onChange={(e) => setPhone(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice Fiscale</label>
                  <input value={fiscalCode} onChange={(e) => setFiscalCode(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Partita IVA</label>
                  <input value={vatNumber} onChange={(e) => setVatNumber(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                </div>
              </div>

              {createError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={createLoading}
                  className="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {createLoading ? "Creazione..." : "Crea Cliente"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
