"use client";

import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { CommissionMovementDetailRead } from "@/lib/types";

const MOVEMENT_LABELS: Record<string, string> = {
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

/** "Da dove arriva" questa provvigione, in termini che hanno senso per chi la
    riceve -- depth_from_producer è già relativo al beneficiario (te) quando
    la riga viene da /commissions/mine/detailed, quindi depth 0 = prodotto
    personalmente da te, depth 1 = da un tuo diretto, depth N = da N livelli
    sotto di te nella rete. */
function levelLabel(depth: number | null): string {
  if (depth === null) return "—";
  if (depth === 0) return "Prodotto da te";
  if (depth === 1) return "Da un tuo diretto";
  return `Da ${depth} livelli sotto di te`;
}

function getStatusColor(status: string): string {
  if (status === "PAID") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  if (status === "REVERSED" || status === "CANCELLED") return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  return "bg-sky-500/10 text-sky-400 border-sky-500/20";
}

async function fetchMyCommissionsDetailed(): Promise<CommissionMovementDetailRead[]> {
  const res = await fetch("/api/proxy/commissions/mine/detailed");
  if (!res.ok) throw new Error("Impossibile caricare le provvigioni");
  return res.json();
}

export function MyCommissions() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["commissions", "mine", "detailed"],
    queryFn: fetchMyCommissionsDetailed,
  });
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-400 light:text-slate-500 gap-2">
        <svg className="animate-spin h-5 w-5 text-orange-500" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <span>Caricamento provvigioni...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
        Errore nel caricamento delle provvigioni.
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500 text-sm">
        Nessuna provvigione maturata al momento.
      </div>
    );
  }

  const totalAccrued = data.filter((m) => m.status === "ACCRUED").reduce((sum, m) => sum + m.amount_cents, 0);
  const totalPaid = data.filter((m) => m.status === "PAID").reduce((sum, m) => sum + m.amount_cents, 0);

  return (
    <div className="space-y-6">
      <div className="overflow-x-auto rounded-xl border border-white/5 light:border-slate-200">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold bg-white/2 light:bg-slate-900/[0.02]">
              <th className="py-3 px-4">Cliente / Contratto</th>
              <th className="py-3 px-4">Provenienza</th>
              <th className="py-3 px-4">Tipo</th>
              <th className="py-3 px-4 text-right">Importo</th>
              <th className="py-3 px-4">Stato</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 light:divide-slate-200">
            {data.map((m) => (
              <Fragment key={m.id}>
                <tr
                  className="text-slate-300 light:text-slate-600 hover:bg-white/5 transition-colors cursor-pointer"
                  onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}
                >
                  <td className="py-3 px-4">
                    <div className="font-medium text-white light:text-slate-900">{m.customer_name}</div>
                    <div className="text-[11px] text-slate-500">{m.product_name}</div>
                  </td>
                  <td className="py-3 px-4">{levelLabel(m.depth_from_producer)}</td>
                  <td className="py-3 px-4">{MOVEMENT_LABELS[m.movement_type] ?? m.movement_type}</td>
                  <td className="py-3 px-4 text-right font-semibold text-orange-400">{euro(m.amount_cents)}</td>
                  <td className="py-3 px-4">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border ${getStatusColor(m.status)}`}>
                      {STATUS_LABELS[m.status] ?? m.status}
                    </span>
                  </td>
                </tr>
                {expandedId === m.id && (
                  <tr className="bg-white/2 light:bg-slate-900/[0.02]">
                    <td colSpan={5} className="px-4 py-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                        <div className="space-y-1.5">
                          <p><span className="text-slate-500">ID Contratto:</span> <span className="font-mono text-[10px] text-slate-400">{m.contract_id}</span></p>
                          <p><span className="text-slate-500">Valore del contratto:</span> <span className="text-slate-300 light:text-slate-600">{euro(m.value_cents)}</span></p>
                          <p><span className="text-slate-500">Prodotto da:</span> <span className="text-slate-300 light:text-slate-600">{m.producer_name}</span></p>
                          <p><span className="text-slate-500">La tua qualifica al momento del calcolo:</span> <span className="font-semibold text-orange-400">{m.rank_at_calculation ?? "—"}</span></p>
                        </div>
                        <div className="space-y-1.5">
                          {m.base_amount_cents !== null && (
                            <p><span className="text-slate-500">Gettone base per la tua qualifica:</span> <span className="text-slate-300 light:text-slate-600">{euro(m.base_amount_cents)}</span></p>
                          )}
                          {m.already_distributed_cents !== null && m.already_distributed_cents > 0 && (
                            <p><span className="text-slate-500">Già riconosciuto ai livelli inferiori:</span> <span className="text-slate-300 light:text-slate-600">{euro(m.already_distributed_cents)}</span></p>
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

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="flex items-center justify-between p-4 rounded-xl bg-gradient-to-r from-sky-600/20 to-sky-500/10 border border-sky-500/30">
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 light:text-slate-600">Totale Maturato</h4>
            <p className="text-[10px] text-slate-400 light:text-slate-500">Non ancora pagato</p>
          </div>
          <span className="text-xl font-bold text-sky-400">{euro(totalAccrued)}</span>
        </div>
        <div className="flex items-center justify-between p-4 rounded-xl bg-gradient-to-r from-orange-600/20 to-amber-500/20 border border-orange-500/30">
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 light:text-slate-600">Totale Pagato</h4>
            <p className="text-[10px] text-slate-400 light:text-slate-500">Già ricevuto</p>
          </div>
          <span className="text-xl font-bold text-emerald-400">{euro(totalPaid)}</span>
        </div>
      </div>
    </div>
  );
}
