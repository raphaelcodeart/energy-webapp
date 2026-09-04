"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { friendlyApiError } from "@/lib/api-error";
import type { CommissionMovementDetailRead } from "@/lib/types";

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

async function fetchContractMovements(contractId: string): Promise<CommissionMovementDetailRead[]> {
  const res = await fetch(`/api/proxy/commissions/movements?contract_id=${contractId}`);
  if (!res.ok) throw new Error("Impossibile caricare le provvigioni di questo contratto.");
  return res.json();
}

export function ContractCommissionsModal({
  contractId,
  onClose,
}: {
  contractId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [payingId, setPayingId] = useState<string | null>(null);
  const [payingAll, setPayingAll] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  const { data: movements, error, isLoading } = useQuery({
    queryKey: ["admin", "commissions", "by-contract", contractId],
    queryFn: () => fetchContractMovements(contractId),
  });

  // Producer (depth 0) first, then the sponsorship chain going up.
  const sorted = [...(movements ?? [])].sort(
    (a, b) => (a.depth_from_producer ?? 0) - (b.depth_from_producer ?? 0)
  );
  const first = sorted[0];
  const totalAccrued = sorted.filter((m) => m.status === "ACCRUED").reduce((sum, m) => sum + m.amount_cents, 0);
  const totalPaid = sorted.filter((m) => m.status === "PAID").reduce((sum, m) => sum + m.amount_cents, 0);
  const totalAll = sorted.reduce((sum, m) => sum + m.amount_cents, 0);
  const anyPayable = sorted.some((m) => m.status === "ACCRUED");

  async function handlePay(movementId: string) {
    setPayingId(movementId);
    setPayError(null);
    try {
      const res = await fetch(`/api/proxy/commissions/movements/${movementId}/pay`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: "Segnata come pagata da amministrazione" }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "commissions"] });
    } catch (err: any) {
      setPayError(err.message || "Impossibile registrare il pagamento.");
    } finally {
      setPayingId(null);
    }
  }

  // Manual mode: settle every beneficiary of this contract at once, right now
  // -- there is no monthly payment batch waiting to run these anyway (see
  // docs/commission-engine-specification.md#trigger), so this just saves
  // clicking "Segna come pagata" once per row.
  async function handlePayAll() {
    setPayingAll(true);
    setPayError(null);
    try {
      const res = await fetch(`/api/proxy/commissions/contracts/${contractId}/pay-all`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: "Liquidazione immediata da amministrazione" }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "commissions"] });
    } catch (err: any) {
      setPayError(err.message || "Impossibile registrare il pagamento.");
    } finally {
      setPayingAll(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-3xl max-h-[85vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <h3 className="text-lg font-bold text-white light:text-slate-900">Provvigioni generate da questo contratto</h3>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              {first && (
                <>
                  <span className="text-xs text-slate-400 light:text-slate-500">{first.customer_name} — {first.product_name}</span>
                  <span className="text-slate-600">·</span>
                  <span className="text-xs text-slate-400 light:text-slate-500">Prodotto da {first.producer_name}</span>
                </>
              )}
            </div>
            <div className="font-mono text-[10px] text-slate-500 mt-1">{contractId}</div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {anyPayable && (
              <button
                onClick={handlePayAll}
                disabled={payingAll}
                className="px-3 py-1.5 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
              >
                {payingAll ? "Liquidazione..." : "Paga tutte ora"}
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {error && (
          <p className="text-sm text-rose-400 mb-4">Impossibile caricare le provvigioni di questo contratto.</p>
        )}
        {payError && (
          <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs mb-4">{payError}</div>
        )}

        <div className="grid grid-cols-3 gap-3 mb-5">
          <div className="rounded-xl bg-white/5 light:bg-slate-900/5 p-3 text-center">
            <p className="text-[10px] text-slate-500 uppercase">Totale movimenti</p>
            <p className="text-lg font-bold text-white light:text-slate-900">{isLoading ? "…" : euro(totalAll)}</p>
          </div>
          <div className="rounded-xl bg-sky-500/10 border border-sky-500/20 p-3 text-center">
            <p className="text-[10px] text-sky-300 uppercase">Maturate</p>
            <p className="text-lg font-bold text-sky-400">{isLoading ? "…" : euro(totalAccrued)}</p>
          </div>
          <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-3 text-center">
            <p className="text-[10px] text-emerald-300 uppercase">Pagate</p>
            <p className="text-lg font-bold text-emerald-400">{isLoading ? "…" : euro(totalPaid)}</p>
          </div>
        </div>

        <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-2">Rete beneficiaria</h4>
        <div className="overflow-x-auto rounded-xl border border-white/5 light:border-slate-200">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold bg-white/2 light:bg-slate-900/[0.02]">
                <th className="py-2 px-3">Promoter beneficiario</th>
                <th className="py-2 px-3">Livello</th>
                <th className="py-2 px-3">Qualifica</th>
                <th className="py-2 px-3">Tipo</th>
                <th className="py-2 px-3 text-right">Importo</th>
                <th className="py-2 px-3">Stato</th>
                <th className="py-2 px-3 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {isLoading && (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">Caricamento...</td></tr>
              )}
              {!isLoading && sorted.length === 0 && (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">Nessuna provvigione ancora calcolata per questo contratto.</td></tr>
              )}
              {sorted.map((m) => (
                <tr key={m.id} className="text-slate-300 light:text-slate-600">
                  <td className="py-2 px-3">
                    <div className="font-medium text-white light:text-slate-900">{m.agent_name}</div>
                    <div className="text-[10px] text-slate-500 font-mono">{m.agent_promoter_code}</div>
                  </td>
                  <td className="py-2 px-3">
                    {m.depth_from_producer === 0 ? "Produttore" : `${m.depth_from_producer}° livello`}
                  </td>
                  <td className="py-2 px-3 text-orange-400 font-semibold">{m.rank_at_calculation ?? "—"}</td>
                  <td className="py-2 px-3">{MOVEMENT_TYPE_LABELS[m.movement_type] ?? m.movement_type}</td>
                  <td className="py-2 px-3 text-right font-semibold text-orange-400">{euro(m.amount_cents)}</td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                      m.status === "PAID"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : "bg-sky-500/10 text-sky-400 border-sky-500/20"
                    }`}>
                      {STATUS_LABELS[m.status] ?? m.status}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    {m.status === "ACCRUED" && (
                      <button
                        onClick={() => handlePay(m.id)}
                        disabled={payingId === m.id}
                        className="px-2.5 py-1 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                      >
                        {payingId === m.id ? "..." : "Segna come pagata"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
