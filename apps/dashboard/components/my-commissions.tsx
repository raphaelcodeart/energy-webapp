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

  if (isLoading) return <p className="text-sm text-slate-500">Caricamento provvigioni...</p>;
  if (error) return <p className="text-sm text-red-600">Errore nel caricamento delle provvigioni.</p>;
  if (!data || data.length === 0) return <p className="text-sm text-slate-500">Nessuna provvigione maturata.</p>;

  const totalCents = data.reduce((sum, m) => sum + m.amount_cents, 0);

  return (
    <div>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left dark:border-slate-800">
            <th className="py-2 pr-4">Tipo</th>
            <th className="py-2 pr-4">Importo</th>
            <th className="py-2 pr-4">Stato</th>
            <th className="py-2 pr-4">Data</th>
          </tr>
        </thead>
        <tbody>
          {data.map((m) => (
            <tr key={m.id} className="border-b border-slate-100 dark:border-slate-900">
              <td className="py-2 pr-4">{MOVEMENT_LABELS[m.movement_type] ?? m.movement_type}</td>
              <td className="py-2 pr-4">{(m.amount_cents / 100).toFixed(2)} {m.currency}</td>
              <td className="py-2 pr-4">{m.status}</td>
              <td className="py-2 pr-4">{m.effective_date}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-sm font-medium">Totale maturato: {(totalCents / 100).toFixed(2)} EUR</p>
    </div>
  );
}
