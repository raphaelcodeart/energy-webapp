"use client";

import { Fragment, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { CommissionLevelTotalsRead, CommissionMovementDetailRead } from "@/lib/types";
import { downloadCsv } from "@/lib/csv-export";

const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  PERSONAL_TOKEN: "Gettone personale",
  ENTREPRENEURIAL_DIFFERENCE: "Differenza imprenditoriale",
  PERSONAL_BONUS: "Bonus personale",
  REVERSAL: "Storno",
};

const STATUS_LABELS: Record<string, string> = {
  ACCRUED: "Maturata",
  PAYABLE: "Liquidabile",
  SCHEDULED: "Programmata",
  PAID: "Pagata",
  REVERSED: "Stornata",
  CANCELLED: "Annullata",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

async function fetchMovements(params: { agentId?: string; status?: string }): Promise<CommissionMovementDetailRead[]> {
  const search = new URLSearchParams();
  if (params.agentId) search.set("agent_id", params.agentId);
  if (params.status) search.set("status_filter", params.status);
  const qs = search.toString();
  const res = await fetch(`/api/proxy/commissions/movements${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error("Impossibile caricare il registro provvigioni.");
  return res.json();
}

async function fetchLevelTotals(): Promise<CommissionLevelTotalsRead[]> {
  const res = await fetch("/api/proxy/commissions/movements/by-level");
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo per livello.");
  return res.json();
}

export function AdminCommissionsPanel({ initialStatusFilter }: { initialStatusFilter?: string }) {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter ?? "ALL");
  const [agentFilter, setAgentFilter] = useState("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [payingId, setPayingId] = useState<string | null>(null);
  const [payError, setPayError] = useState<string | null>(null);

  const { data: movements, error: movementsError, isLoading } = useQuery({
    queryKey: ["admin", "commissions", "movements"],
    queryFn: () => fetchMovements({}),
  });
  const { data: levelTotals } = useQuery({
    queryKey: ["admin", "commissions", "by-level"],
    queryFn: fetchLevelTotals,
  });

  const agents = useMemo(() => {
    const map = new Map<string, string>();
    (movements ?? []).forEach((m) => map.set(m.agent_id, `${m.agent_name} (${m.agent_promoter_code})`));
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [movements]);

  const filtered = (movements ?? []).filter(
    (m) => (statusFilter === "ALL" || m.status === statusFilter) && (agentFilter === "ALL" || m.agent_id === agentFilter)
  );

  const totalAccrued = filtered.filter((m) => m.status === "ACCRUED").reduce((sum, m) => sum + m.amount_cents, 0);
  const totalPaid = filtered.filter((m) => m.status === "PAID").reduce((sum, m) => sum + m.amount_cents, 0);

  async function handlePay(movementId: string) {
    setPayingId(movementId);
    setPayError(null);
    try {
      const res = await fetch(`/api/proxy/commissions/movements/${movementId}/pay`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: "Segnata come pagata da amministrazione" }),
      });
      if (!res.ok) throw new Error(await res.text());
      await queryClient.invalidateQueries({ queryKey: ["admin", "commissions"] });
    } catch (err: any) {
      setPayError(err.message || "Impossibile registrare il pagamento.");
    } finally {
      setPayingId(null);
    }
  }

  function handleExportCsv() {
    downloadCsv(
      `provvigioni_${new Date().toISOString().slice(0, 10)}`,
      ["ID Movimento", "Contratto", "Cliente", "Prodotto", "Promoter", "Codice Promoter", "Livello da produttore", "Qualifica al calcolo", "Tipo", "Importo (EUR)", "Stato", "Data Maturazione", "Data Pagamento"],
      filtered.map((m) => [
        m.id, m.contract_id, m.customer_name, m.product_name, m.agent_name, m.agent_promoter_code,
        m.depth_from_producer ?? "", m.rank_at_calculation ?? "", MOVEMENT_TYPE_LABELS[m.movement_type] ?? m.movement_type,
        (m.amount_cents / 100).toFixed(2), STATUS_LABELS[m.status] ?? m.status, m.effective_date, m.paid_date ?? "",
      ])
    );
  }

  return (
    <div className="space-y-6">
      {/* Per-level rollup -- "per ogni livello: contratti attivi, fatturato, provvigioni" */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="p-5 pb-3">
          <h3 className="text-sm font-semibold text-white light:text-slate-900">Distribuzione per livello di rete</h3>
          <p className="text-[11px] text-slate-500 mt-1">
            Livello 0 = il promoter che ha prodotto direttamente il contratto; livello N = quanti passaggi di sponsorizzazione sopra di lui.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 px-5">Livello</th>
                <th className="py-2 px-5 text-right">Contratti</th>
                <th className="py-2 px-5 text-right">Fatturato</th>
                <th className="py-2 px-5 text-right">Provvigioni generate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {(levelTotals ?? []).map((row) => (
                <tr key={row.depth} className="text-slate-300 light:text-slate-600">
                  <td className="py-2 px-5 font-semibold text-white light:text-slate-900">
                    {row.depth === 0 ? "0 (produttore)" : row.depth}
                  </td>
                  <td className="py-2 px-5 text-right">{row.contracts}</td>
                  <td className="py-2 px-5 text-right">{euro(row.value_cents)}</td>
                  <td className="py-2 px-5 text-right font-semibold text-orange-400">{euro(row.commission_cents)}</td>
                </tr>
              ))}
              {(levelTotals ?? []).length === 0 && (
                <tr><td colSpan={4} className="text-center py-6 text-slate-500">Nessun dato disponibile.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* KPI + filters + export */}
      <div className="flex flex-col lg:flex-row gap-4">
        <div className="flex-1 grid grid-cols-2 gap-4">
          <div className="glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Maturate (nel filtro)</p>
            <p className="text-xl font-bold text-sky-400">{euro(totalAccrued)}</p>
          </div>
          <div className="glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Pagate (nel filtro)</p>
            <p className="text-xl font-bold text-emerald-400">{euro(totalPaid)}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
          >
            <option value="ALL">Tutti gli stati</option>
            <option value="ACCRUED">Solo maturate</option>
            <option value="PAID">Solo pagate</option>
          </select>
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500 max-w-[220px]"
          >
            <option value="ALL">Tutti i promoter</option>
            {agents.map(([id, label]) => (
              <option key={id} value={id}>{label}</option>
            ))}
          </select>
          <button
            onClick={handleExportCsv}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Esporta CSV
          </button>
        </div>
      </div>

      {payError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{payError}</div>
      )}
      {movementsError && (
        <p className="text-sm text-rose-400">Impossibile caricare il registro provvigioni.</p>
      )}

      {/* Movement ledger with full traceability */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-3 px-5">Cliente / Contratto</th>
                <th className="py-3 px-5">Promoter beneficiario</th>
                <th className="py-3 px-5">Livello</th>
                <th className="py-3 px-5">Tipo</th>
                <th className="py-3 px-5 text-right">Importo</th>
                <th className="py-3 px-5">Stato</th>
                <th className="py-3 px-5 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {isLoading && (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">Caricamento...</td></tr>
              )}
              {!isLoading && filtered.length === 0 && (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">Nessun movimento corrisponde ai filtri.</td></tr>
              )}
              {filtered.map((m) => (
                <Fragment key={m.id}>
                  <tr
                    className="text-slate-300 light:text-slate-600 hover:bg-white/5 transition-colors cursor-pointer"
                    onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}
                  >
                    <td className="py-3 px-5">
                      <div className="font-medium text-white light:text-slate-900">{m.customer_name}</div>
                      <div className="text-[10px] text-slate-500 font-mono">{m.contract_id}</div>
                    </td>
                    <td className="py-3 px-5">
                      <div>{m.agent_name}</div>
                      <div className="text-[10px] text-slate-500 font-mono">{m.agent_promoter_code}</div>
                    </td>
                    <td className="py-3 px-5">
                      {m.depth_from_producer === 0 ? "Produttore" : `${m.depth_from_producer}° livello`}
                    </td>
                    <td className="py-3 px-5">{MOVEMENT_TYPE_LABELS[m.movement_type] ?? m.movement_type}</td>
                    <td className="py-3 px-5 text-right font-semibold text-orange-400">{euro(m.amount_cents)}</td>
                    <td className="py-3 px-5">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        m.status === "PAID"
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          : "bg-sky-500/10 text-sky-400 border-sky-500/20"
                      }`}>
                        {STATUS_LABELS[m.status] ?? m.status}
                      </span>
                    </td>
                    <td className="py-3 px-5 text-right">
                      {m.status === "ACCRUED" && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handlePay(m.id); }}
                          disabled={payingId === m.id}
                          className="px-2.5 py-1 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                        >
                          {payingId === m.id ? "..." : "Segna come pagata"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedId === m.id && (
                    <tr className="bg-white/2 light:bg-slate-900/[0.02]">
                      <td colSpan={7} className="px-5 py-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                          <div className="space-y-1.5">
                            <p><span className="text-slate-500">Prodotto:</span> <span className="text-slate-300 light:text-slate-600">{m.product_name}</span></p>
                            <p><span className="text-slate-500">Valore del contratto:</span> <span className="text-slate-300 light:text-slate-600">{euro(m.value_cents)}</span></p>
                            <p><span className="text-slate-500">Produttore del contratto:</span> <span className="text-slate-300 light:text-slate-600">{m.producer_name}</span></p>
                            <p><span className="text-slate-500">Qualifica del promoter al momento del calcolo:</span> <span className="font-semibold text-orange-400">{m.rank_at_calculation ?? "—"}</span></p>
                            <p><span className="text-slate-500">Qualifica attuale del promoter:</span> <span className="text-slate-300 light:text-slate-600">{m.agent_current_rank_code ?? "—"}</span></p>
                          </div>
                          <div className="space-y-1.5">
                            {m.base_amount_cents !== null && (
                              <p><span className="text-slate-500">Gettone base per la qualifica:</span> <span className="text-slate-300 light:text-slate-600">{euro(m.base_amount_cents)}</span></p>
                            )}
                            {m.already_distributed_cents !== null && m.already_distributed_cents > 0 && (
                              <p><span className="text-slate-500">Già riconosciuto ai livelli inferiori:</span> <span className="text-slate-300 light:text-slate-600">{euro(m.already_distributed_cents)}</span></p>
                            )}
                            {m.entrepreneurial_difference_cents !== null && m.entrepreneurial_difference_cents > 0 && (
                              <p><span className="text-slate-500">Differenza imprenditoriale riconosciuta:</span> <span className="text-slate-300 light:text-slate-600">{euro(m.entrepreneurial_difference_cents)}</span></p>
                            )}
                            <p><span className="text-slate-500">Data maturazione:</span> <span className="text-slate-300 light:text-slate-600">{new Date(m.effective_date).toLocaleDateString("it-IT")}</span></p>
                            {m.paid_date && (
                              <p><span className="text-slate-500">Data pagamento:</span> <span className="text-emerald-400">{new Date(m.paid_date).toLocaleDateString("it-IT")}</span></p>
                            )}
                          </div>
                        </div>
                        {m.explanation && (
                          <div className="mt-3 p-3 rounded-xl bg-orange-500/5 border border-orange-500/15 text-orange-200 light:text-orange-700">
                            <span className="font-bold uppercase tracking-wider text-[10px] block mb-1">Perché questo importo</span>
                            {m.explanation}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
