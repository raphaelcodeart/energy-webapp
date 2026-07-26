"use client";

import { useState } from "react";
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
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo.");
  return res.json();
}

async function fetchBranchContracts(agentId: string): Promise<BranchContractRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch-contracts`);
  if (!res.ok) throw new Error("Impossibile caricare i contratti.");
  return res.json();
}

export function NetworkNodeDetailModal({
  agentId,
  displayName,
  onClose,
}: {
  agentId: string;
  displayName: string;
  onClose: () => void;
}) {
  const [onlyProblems, setOnlyProblems] = useState(false);
  const { data: summary, error: summaryError, isLoading: summaryLoading } = useQuery({
    queryKey: ["network", "node-detail", "summary", agentId],
    queryFn: () => fetchBranchSummary(agentId),
  });
  const { data: contracts, error: contractsError, isLoading: contractsLoading } = useQuery({
    queryKey: ["network", "node-detail", "contracts", agentId],
    queryFn: () => fetchBranchContracts(agentId),
  });

  const self = summary?.agents.find((a) => a.depth === 0);
  const totals = summary?.totals;
  const filteredContracts = (contracts ?? []).filter((c) => !onlyProblems || c.is_problem);
  const totalValue = (contracts ?? []).reduce((sum, c) => sum + c.value_cents, 0);
  const myTotalCommission = (contracts ?? []).reduce((sum, c) => sum + (c.my_commission_cents ?? 0), 0);
  const hasViewerCommission = (contracts ?? []).some((c) => c.my_commission_cents !== null);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-3xl max-h-[85vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <div className="flex items-start justify-between mb-4 gap-3">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-full bg-gradient-to-br from-orange-600 to-amber-500 flex items-center justify-center text-white font-bold text-lg shrink-0">
              {displayName.trim().charAt(0).toUpperCase() || "?"}
            </div>
            <div>
              <h3 className="text-lg font-bold text-white light:text-slate-900">{displayName}</h3>
              <div className="flex items-center gap-2 mt-0.5">
                {self?.promoter_code && (
                  <span className="font-mono text-[10px] text-slate-500">{self.promoter_code}</span>
                )}
                {self?.rank_code && (
                  <span className="px-2 py-0.5 text-[10px] font-bold rounded-md border bg-white/5 light:bg-slate-900/5 text-slate-300 light:text-slate-600 border-white/10 light:border-slate-300">
                    {self.rank_code}
                  </span>
                )}
                {self?.status && (
                  <span className={`px-2 py-0.5 text-[10px] font-bold rounded-md border ${
                    self.status === "ACTIVE"
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                  }`}>
                    {self.status}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer shrink-0"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {(summaryError || contractsError) && (
          <p className="text-sm text-rose-400 mb-4">Impossibile caricare i dettagli di questo nodo.</p>
        )}

        {/* Stats grid -- people below, contracts, commission generated within this subtree */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3 text-center">
            <p className="text-[10px] text-slate-500 uppercase">Persone sotto</p>
            <p className="text-lg font-bold text-white light:text-slate-900">
              {summaryLoading ? "…" : totals?.people_total ?? 0}
            </p>
          </div>
          <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3 text-center">
            <p className="text-[10px] text-slate-500 uppercase">Livelli sotto</p>
            <p className="text-lg font-bold text-white light:text-slate-900">
              {summaryLoading ? "…" : totals?.levels_below ?? 0}
            </p>
          </div>
          <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3 text-center">
            <p className="text-[10px] text-slate-500 uppercase">Contratti totali</p>
            <p className="text-lg font-bold text-white light:text-slate-900">
              {summaryLoading ? "…" : totals?.contracts ?? 0}
            </p>
          </div>
          <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3 text-center">
            <p className="text-[10px] text-slate-500 uppercase">In lavorazione</p>
            <p className="text-lg font-bold text-sky-400">
              {summaryLoading ? "…" : totals?.contracts_in_progress ?? 0}
            </p>
          </div>
          <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3 text-center">
            <p className="text-[10px] text-slate-500 uppercase">Chiusi</p>
            <p className="text-lg font-bold text-emerald-400">
              {summaryLoading ? "…" : totals?.contracts_closed ?? 0}
            </p>
          </div>
          <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3 text-center">
            <p className="text-[10px] text-slate-500 uppercase">Rifiutati</p>
            <p className="text-lg font-bold text-rose-400">
              {summaryLoading ? "…" : totals?.contracts_rejected ?? 0}
            </p>
          </div>
          <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3 text-center">
            <p className="text-[10px] text-slate-500 uppercase">Valore creato</p>
            <p className="text-lg font-bold text-white light:text-slate-900">
              {contractsLoading ? "…" : euro(totalValue)}
            </p>
          </div>
          <div className="rounded-xl bg-orange-500/10 border border-orange-500/20 p-3 text-center">
            <p className="text-[10px] text-orange-300 uppercase">
              {hasViewerCommission ? "La tua provvigione" : "Provvigioni branch"}
            </p>
            <p className="text-lg font-bold text-orange-400">
              {contractsLoading
                ? "…"
                : hasViewerCommission
                  ? euro(myTotalCommission)
                  : euro(totals?.commission_cents ?? 0)}
            </p>
          </div>
        </div>

        {/* Per-contract detail */}
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-semibold text-white light:text-slate-900">Contratti in questo ramo</h4>
          <label className="flex items-center gap-2 text-xs text-slate-400 light:text-slate-500 cursor-pointer">
            <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} className="cursor-pointer" />
            Solo con problemi
          </label>
        </div>
        <div className="overflow-x-auto rounded-xl border border-white/5 light:border-slate-200">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold bg-white/2 light:bg-slate-900/[0.02]">
                <th className="py-2 px-3">Cliente</th>
                <th className="py-2 px-3">Prodotto</th>
                <th className="py-2 px-3">Stato</th>
                <th className="py-2 px-3 text-right">Valore</th>
                <th className="py-2 px-3 text-right">{hasViewerCommission ? "Tua provvigione" : "Provvigione"}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {filteredContracts.map((c) => (
                <tr key={c.contract_id} className="text-slate-300 light:text-slate-600">
                  <td className="py-2 px-3">
                    <div className="font-medium text-white light:text-slate-900">{c.customer_name}</div>
                    <div className="text-[10px] text-slate-500">{c.producer_name}</div>
                  </td>
                  <td className="py-2 px-3">{c.product_name}</td>
                  <td className="py-2 px-3">
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
                  <td className="py-2 px-3 text-right text-slate-300 light:text-slate-600">{euro(c.value_cents)}</td>
                  <td className="py-2 px-3 text-right font-semibold text-orange-400">
                    {hasViewerCommission ? euro(c.my_commission_cents ?? 0) : euro(c.commission_cents)}
                  </td>
                </tr>
              ))}
              {filteredContracts.length === 0 && !contractsLoading && (
                <tr><td colSpan={5} className="text-center py-6 text-slate-500">Nessun contratto in questo ramo.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
