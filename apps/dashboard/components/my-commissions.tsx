"use client";

import { useQuery } from "@tanstack/react-query";
import type { CommissionMovementRead } from "@/lib/types";

const MOVEMENT_LABELS: Record<string, string> = {
  PERSONAL_TOKEN: "Gettone personale",
  ENTREPRENEURIAL_DIFFERENCE: "Differenza imprenditoriale",
  PERSONAL_BONUS: "Bonus personale",
  REVERSAL: "Storno",
};

async function fetchMyCommissions(): Promise<CommissionMovementRead[]> {
  const res = await fetch("/api/proxy/commissions/mine");
  if (!res.ok) throw new Error("Impossibile caricare le provvigioni");
  return res.json();
}

export function MyCommissions() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["commissions", "mine"],
    queryFn: fetchMyCommissions,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-400 gap-2">
        <svg className="animate-spin h-5 w-5 text-violet-500" fill="none" viewBox="0 0 24 24">
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

  const totalCents = data.reduce((sum, m) => sum + m.amount_cents, 0);

  const getStatusColor = (status: string) => {
    switch (status.toUpperCase()) {
      case "SETTLED":
      case "APPROVED":
      case "PAID":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      case "PENDING":
        return "bg-amber-500/10 text-amber-400 border-amber-500/20";
      case "REVERSED":
      case "CANCELLED":
        return "bg-rose-500/10 text-rose-400 border-rose-500/20";
      default:
        return "bg-slate-500/10 text-slate-400 border-slate-500/20";
    }
  };

  return (
    <div className="space-y-6">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-white/5 text-slate-400 font-semibold">
              <th className="pb-3 pr-4">Tipo</th>
              <th className="pb-3 pr-4">Importo</th>
              <th className="pb-3 pr-4">Stato</th>
              <th className="pb-3 pr-4">Data Efficacia</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {data.map((m) => (
              <tr key={m.id} className="text-slate-300 hover:bg-white/5 transition-colors">
                <td className="py-3.5 pr-4 font-medium text-white">
                  {MOVEMENT_LABELS[m.movement_type] ?? m.movement_type}
                </td>
                <td className="py-3.5 pr-4 font-semibold text-emerald-400">
                  {(m.amount_cents / 100).toFixed(2)} {m.currency}
                </td>
                <td className="py-3.5 pr-4">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border ${getStatusColor(m.status)}`}>
                    {m.status}
                  </span>
                </td>
                <td className="py-3.5 pr-4 text-xs font-mono text-slate-400">
                  {m.effective_date}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between p-4 rounded-xl bg-gradient-to-r from-violet-600/20 to-cyan-500/20 border border-violet-500/30">
        <div>
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">Totale Maturato</h4>
          <p className="text-[10px] text-slate-400">Aggiornato in tempo reale</p>
        </div>
        <span className="text-xl font-bold text-emerald-400">
          {(totalCents / 100).toFixed(2)} EUR
        </span>
      </div>
    </div>
  );
}
