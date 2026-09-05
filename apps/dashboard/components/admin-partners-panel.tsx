"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { PartnerRead } from "@/lib/types";

async function fetchPartners(): Promise<PartnerRead[]> {
  const res = await fetch("/api/proxy/partners");
  if (!res.ok) throw new Error("Impossibile caricare i partner.");
  return res.json();
}

/** Anagrafica dei fornitori esterni che Lial Energy fa da broker per (es.
    Eviso) -- vedi docs/cashback-partner-invoices-plan.md. Il cliente sceglie
    da questo elenco quando carica una fattura da riscattare. */
export function AdminPartnersPanel() {
  const queryClient = useQueryClient();
  const { data: partners, error: loadError } = useQuery({
    queryKey: ["admin", "partners"],
    queryFn: fetchPartners,
  });

  const [name, setName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [toggleId, setToggleId] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/partners", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "partners"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il partner.");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleToggleActive(partner: PartnerRead) {
    setToggleId(partner.id);
    try {
      const res = await fetch(`/api/proxy/partners/${partner.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !partner.is_active }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "partners"] });
    } finally {
      setToggleId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h3 className="text-sm font-semibold text-white light:text-slate-900 mb-1">Nuovo fornitore partner</h3>
        <p className="text-xs text-slate-500 mb-4">
          Un fornitore esterno di cui Lial Energy è broker (es. Eviso). Comparirà nell'elenco che il cliente vede quando carica una fattura da riscattare.
        </p>
        <form onSubmit={handleCreate} className="flex items-end gap-3">
          <div className="space-y-1 flex-1 max-w-sm">
            <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Es. Eviso"
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
          </div>
          <button
            type="submit"
            disabled={createLoading}
            className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {createLoading ? "..." : "Aggiungi"}
          </button>
        </form>
        {createError && (
          <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
        )}
      </div>

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="p-5 pb-3">
          <h3 className="text-sm font-semibold text-white light:text-slate-900">Fornitori partner</h3>
        </div>
        {loadError && <p className="px-5 pb-3 text-sm text-rose-400">Impossibile caricare i partner.</p>}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 px-5">Nome</th>
                <th className="py-2 px-5">Stato</th>
                <th className="py-2 px-5 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {partners === undefined ? (
                <tr><td colSpan={3} className="text-center py-6 text-slate-500">Caricamento...</td></tr>
              ) : partners.length === 0 ? (
                <tr><td colSpan={3} className="text-center py-6 text-slate-500">Nessun partner ancora.</td></tr>
              ) : (
                partners.map((p) => (
                  <tr key={p.id} className="text-slate-300 light:text-slate-600">
                    <td className="py-2 px-5 font-medium text-white light:text-slate-900">{p.name}</td>
                    <td className="py-2 px-5">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        p.is_active
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          : "bg-slate-500/10 text-slate-400 border-slate-500/20"
                      }`}>
                        {p.is_active ? "Attivo" : "Disattivato"}
                      </span>
                    </td>
                    <td className="py-2 px-5 text-right">
                      <button
                        onClick={() => handleToggleActive(p)}
                        disabled={toggleId === p.id}
                        className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                      >
                        {toggleId === p.id ? "..." : p.is_active ? "Disattiva" : "Riattiva"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
