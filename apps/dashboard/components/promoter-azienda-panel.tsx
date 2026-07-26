"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { BranchContractRead, BranchSummaryRead } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

async function fetchBranchSummary(agentId: string): Promise<BranchSummaryRead> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch-summary`);
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo della rete.");
  return res.json();
}

async function fetchBranchContracts(agentId: string): Promise<BranchContractRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch-contracts`);
  if (!res.ok) throw new Error("Impossibile caricare i contratti della rete.");
  return res.json();
}

export function PromoterAziendaPanel({ agentId }: { agentId: string }) {
  const { data: summary, error: summaryError, isLoading: summaryLoading } = useQuery({
    queryKey: ["promoter", "branch-summary", agentId],
    queryFn: () => fetchBranchSummary(agentId),
  });
  const { data: contracts, error: contractsError } = useQuery({
    queryKey: ["promoter", "branch-contracts", agentId],
    queryFn: () => fetchBranchContracts(agentId),
  });
  const [onlyProblems, setOnlyProblems] = useState(false);

  const perLevel = useMemo(() => {
    if (!summary) return [];
    const map = new Map<number, { depth: number; agentCount: number; contracts: number; commission: number }>();
    for (const a of summary.agents) {
      const entry = map.get(a.depth) ?? { depth: a.depth, agentCount: 0, contracts: 0, commission: 0 };
      entry.agentCount += 1;
      entry.contracts += a.contracts_total;
      entry.commission += a.commission_cents;
      map.set(a.depth, entry);
    }
    return Array.from(map.values()).sort((a, b) => a.depth - b.depth);
  }, [summary]);

  const directCount = summary?.agents.filter((a) => a.depth === 1).length ?? 0;
  const totalProblems = summary?.agents.reduce((sum, a) => sum + a.contracts_problem, 0) ?? 0;

  const filteredContracts = (contracts ?? []).filter((c) => !onlyProblems || c.is_problem);

  return (
    <div className="space-y-6">
      {(summaryError || contractsError) && (
        <p className="text-sm text-rose-400">Impossibile caricare i dati della rete.</p>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Diretti</p>
          <p className="text-xl font-bold text-white light:text-slate-900">{summaryLoading ? "…" : directCount}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Rete totale</p>
          <p className="text-xl font-bold text-white light:text-slate-900">
            {summaryLoading ? "…" : (summary?.agents.length ?? 0) - 1 /* exclude self at depth 0 */}
          </p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Contratti totali</p>
          <p className="text-xl font-bold text-white light:text-slate-900">{summaryLoading ? "…" : summary?.totals.contracts ?? 0}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Provvigioni totali</p>
          <p className="text-xl font-bold text-orange-400">{summaryLoading ? "…" : euro(summary?.totals.commission_cents ?? 0)}</p>
        </div>
      </div>

      {totalProblems > 0 && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm">
          <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {totalProblems} {totalProblems === 1 ? "contratto ha" : "contratti hanno"} bisogno di attenzione nella tua rete.
        </div>
      )}

      {/* Per-level breakdown */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="p-5 pb-0">
          <h3 className="text-sm font-semibold text-white light:text-slate-900">Riepilogo per livello</h3>
        </div>
        <div className="overflow-x-auto p-5">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 pr-4">Livello</th>
                <th className="py-2 pr-4">Persone</th>
                <th className="py-2 pr-4">Contratti</th>
                <th className="py-2 pr-4 text-right">Provvigioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {perLevel.map((row) => (
                <tr key={row.depth} className="text-slate-300 light:text-slate-600">
                  <td className="py-2 pr-4 font-medium text-white light:text-slate-900">
                    {row.depth === 0 ? "Tu" : `Livello ${row.depth}`}
                  </td>
                  <td className="py-2 pr-4">{row.agentCount}</td>
                  <td className="py-2 pr-4">{row.contracts}</td>
                  <td className="py-2 pr-4 text-right font-semibold text-orange-400">{euro(row.commission)}</td>
                </tr>
              ))}
              {perLevel.length === 0 && !summaryLoading && (
                <tr><td colSpan={4} className="text-center py-6 text-slate-500">Nessun dato disponibile.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Per-agent breakdown */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="p-5 pb-0">
          <h3 className="text-sm font-semibold text-white light:text-slate-900">Contratti per persona</h3>
        </div>
        <div className="overflow-x-auto p-5">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 pr-4">Nome</th>
                <th className="py-2 pr-4">Livello</th>
                <th className="py-2 pr-4">Totali</th>
                <th className="py-2 pr-4">Processati</th>
                <th className="py-2 pr-4">In lavorazione</th>
                <th className="py-2 pr-4">Problemi</th>
                <th className="py-2 pr-4 text-right">Provvigioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {(summary?.agents ?? []).map((a) => (
                <tr key={a.agent_id} className="text-slate-300 light:text-slate-600">
                  <td className="py-2 pr-4 font-medium text-white light:text-slate-900">{a.display_name}</td>
                  <td className="py-2 pr-4">{a.depth === 0 ? "Tu" : a.depth}</td>
                  <td className="py-2 pr-4">{a.contracts_total}</td>
                  <td className="py-2 pr-4 text-emerald-400">{a.contracts_processed}</td>
                  <td className="py-2 pr-4 text-amber-400">{a.contracts_in_progress}</td>
                  <td className="py-2 pr-4">
                    {a.contracts_problem > 0 ? (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-rose-500/10 text-rose-400 border-rose-500/20">
                        {a.contracts_problem}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="py-2 pr-4 text-right font-semibold text-orange-400">{euro(a.commission_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Contract-level detail with contact action */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="p-5 pb-0 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white light:text-slate-900">Contratti della rete</h3>
          <label className="flex items-center gap-2 text-xs text-slate-400 light:text-slate-500 cursor-pointer">
            <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} className="cursor-pointer" />
            Solo con problemi
          </label>
        </div>
        <div className="overflow-x-auto p-5">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 pr-4">Cliente</th>
                <th className="py-2 pr-4">Prodotto</th>
                <th className="py-2 pr-4">Venditore</th>
                <th className="py-2 pr-4">Stato</th>
                <th className="py-2 pr-4 text-right">Provvigione</th>
                <th className="py-2 pr-4 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {filteredContracts.map((c) => (
                <tr key={c.contract_id} className="text-slate-300 light:text-slate-600">
                  <td className="py-2 pr-4">
                    <div className="font-medium text-white light:text-slate-900">{c.customer_name}</div>
                    <div className="font-mono text-[10px] text-slate-500">{c.customer_id}</div>
                  </td>
                  <td className="py-2 pr-4">{c.product_name}</td>
                  <td className="py-2 pr-4">{c.producer_name}</td>
                  <td className="py-2 pr-4">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                      c.is_problem
                        ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                        : c.status === "ACTIVE" || c.status === "RENEWED"
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                    }`}>
                      {STATUS_LABELS[c.status] ?? c.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right font-semibold text-orange-400">{euro(c.commission_cents)}</td>
                  <td className="py-2 pr-4 text-right">
                    {c.customer_email && (
                      <a
                        href={`mailto:${c.customer_email}${c.is_problem ? `?subject=${encodeURIComponent("La tua fornitura Lial Energy")}&body=${encodeURIComponent("Ciao, ho notato che il tuo contratto è in attesa di documenti. Posso aiutarti a completarli?")}` : ""}`}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        Contatta
                      </a>
                    )}
                  </td>
                </tr>
              ))}
              {filteredContracts.length === 0 && (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">Nessun contratto trovato.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
