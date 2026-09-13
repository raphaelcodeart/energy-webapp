"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { downloadCsv } from "@/lib/csv-export";
import { Pagination, usePagination } from "@/components/pagination";
import {
  euro, formatDate, lialCash, movementCategory, movementDirection, movementLabel,
  movementReferenceLink, movementSignedAmountCents,
} from "@/lib/accounting-format";
import type { FinancialMovementRead } from "@/lib/types";

type MovementFilter = "ALL" | "LIALCASH" | "BANK_TRANSFER" | "CARD";

const FILTER_TABS: { key: MovementFilter; label: string }[] = [
  { key: "ALL", label: "Tutte" },
  { key: "LIALCASH", label: "LialCash" },
  { key: "BANK_TRANSFER", label: "Bonifico" },
  { key: "CARD", label: "Carta" },
];

const CATEGORY_COLORS: Record<string, string> = {
  Ricarica: "bg-sky-500/10 text-sky-400 border-sky-500/20",
  Cashback: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  Pagamento: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  Trasferimento: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  Storno: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  Altro: "bg-slate-500/10 text-slate-400 border-slate-500/20",
};

/** ↓ green pill for an "entrata" (money in), ↑ rose pill for an "uscita"
    (money out) -- the single clearest signal on the whole row, per the
    user's explicit "metti ben chiaro se è entrata o uscita" request. */
function DirectionBadge({ direction }: { direction: "in" | "out" }) {
  return direction === "in" ? (
    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-emerald-500/15 text-emerald-400 shrink-0" title="Entrata">
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
      </svg>
    </span>
  ) : (
    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-rose-500/15 text-rose-400 shrink-0" title="Uscita">
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
      </svg>
    </span>
  );
}

/** Symbol telling LialCash apart from real Euro at a glance -- a coin for
    credits, a euro sign for real money, plus (for Euro) the payment method
    underneath. Per the user's explicit request for a currency symbol. */
function CurrencyBadge({ m }: { m: FinancialMovementRead }) {
  if (m.currency === "LIALCASH") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-orange-500/10 border border-orange-500/20 text-orange-400 text-[11px] font-bold whitespace-nowrap">
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <circle cx="12" cy="12" r="9" strokeWidth={1.75} />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 7v10M9.5 9.5c0-1 .9-1.8 2.5-1.8s2.5.7 2.5 1.6c0 2.2-5 1-5 3.2 0 .9 1 1.7 2.5 1.7s2.5-.8 2.5-1.8" />
        </svg>
        LialCash
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-[11px] font-bold whitespace-nowrap">
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M14.121 15.536c-1.171 1.952-3.07 1.952-4.242 0-1.172-1.953-1.172-5.119 0-7.072 1.171-1.952 3.07-1.952 4.242 0M8 10.5h4m-4 3h4" />
      </svg>
      {m.payment_method === "CARD" ? "Carta" : m.payment_method === "BANK_TRANSFER" ? "Bonifico" : "Euro"}
    </span>
  );
}

async function fetchMyMovements(): Promise<FinancialMovementRead[]> {
  const res = await fetch("/api/proxy/accounting/mine");
  if (!res.ok) throw new Error("Impossibile caricare la contabilità.");
  return res.json();
}

export function AccountingPanel() {
  const [filter, setFilter] = useState<MovementFilter>("ALL");

  const { data: movements, error } = useQuery({
    queryKey: ["accounting", "mine"],
    queryFn: fetchMyMovements,
  });

  const list = movements ?? [];

  const matchesFilter = (m: FinancialMovementRead, f: MovementFilter) => {
    if (f === "ALL") return true;
    if (f === "LIALCASH") return m.currency === "LIALCASH";
    return m.currency === "EUR" && m.payment_method === f;
  };

  const filteredList = list.filter((m) => matchesFilter(m, filter));

  const totalLialCashCents = list.filter((m) => m.currency === "LIALCASH").reduce((sum, m) => sum + movementSignedAmountCents(m), 0);
  const totalBankTransferCents = list
    .filter((m) => m.currency === "EUR" && m.payment_method === "BANK_TRANSFER")
    .reduce((sum, m) => sum + Math.abs(m.amount_cents), 0);
  const totalCardCents = list
    .filter((m) => m.currency === "EUR" && m.payment_method === "CARD")
    .reduce((sum, m) => sum + Math.abs(m.amount_cents), 0);

  // Paginates the FILTERED movements; CSV export stays on filteredList.
  const pagination = usePagination(filteredList);

  function handleExportCsv() {
    downloadCsv(
      `contabilita-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Data", "Tipo", "Movimento", "Descrizione", "Riferimento", "Valuta", "Metodo di pagamento", "Entrata/Uscita", "Importo", "Nota"],
      filteredList.map((m) => [
        formatDate(m.created_at),
        movementCategory(m),
        movementLabel(m),
        m.product_name ?? "",
        movementReferenceLink(m, "/customer")?.label ?? "",
        m.currency === "LIALCASH" ? "LialCash" : "EUR",
        m.payment_method ? (m.payment_method === "CARD" ? "Carta" : "Bonifico") : "",
        movementDirection(m) === "in" ? "Entrata" : "Uscita",
        (Math.abs(m.amount_cents) / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        m.note ?? "",
      ])
    );
  }

  if (error) {
    return <p className="text-sm text-rose-400">Impossibile caricare la contabilità.</p>;
  }

  return (
    <div className="space-y-6">
      {/* Totals */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-gradient-to-br from-orange-500/10 to-transparent">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Saldo netto LialCash</p>
          <p className={`text-xl font-bold ${totalLialCashCents < 0 ? "text-rose-400" : "text-orange-400"}`}>
            {lialCash(totalLialCashCents)}
          </p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Pagato con Bonifico</p>
          <p className="text-xl font-bold text-white light:text-slate-900">{euro(totalBankTransferCents)}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Pagato con Carta (Stripe)</p>
          <p className="text-xl font-bold text-white light:text-slate-900">{euro(totalCardCents)}</p>
        </div>
      </div>

      {/* Filters + export */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {FILTER_TABS.map((tab) => {
            const count = list.filter((m) => matchesFilter(m, tab.key)).length;
            return (
              <button
                key={tab.key}
                onClick={() => setFilter(tab.key)}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                  filter === tab.key
                    ? "bg-orange-600 border-orange-600 text-white"
                    : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                }`}
              >
                {tab.label}
                <span className="ml-1.5 opacity-70">({count})</span>
              </button>
            );
          })}
        </div>
        <button
          onClick={handleExportCsv}
          disabled={filteredList.length === 0}
          className="px-3.5 py-1.5 rounded-xl text-xs font-semibold border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10 transition cursor-pointer disabled:opacity-40"
        >
          Scarica report CSV
        </button>
      </div>

      {/* Movements */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 px-5">Data</th>
                <th className="py-2 px-5"></th>
                <th className="py-2 px-5">Tipo</th>
                <th className="py-2 px-5">Movimento</th>
                <th className="py-2 px-5">Riferimento</th>
                <th className="py-2 px-5">Valuta</th>
                <th className="py-2 px-5 text-right">Importo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {movements === undefined ? (
                <tr><td colSpan={7} className="text-center py-6 text-slate-500">Caricamento...</td></tr>
              ) : filteredList.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-6 text-slate-500">Nessuna transazione in questa categoria.</td></tr>
              ) : (
                pagination.pageItems.map((m) => {
                  const direction = movementDirection(m);
                  const category = movementCategory(m);
                  const ref = movementReferenceLink(m, "/customer");
                  return (
                    <tr key={m.id} className="text-slate-300 light:text-slate-600">
                      <td className="py-2.5 px-5 whitespace-nowrap text-slate-400 light:text-slate-500">{formatDate(m.created_at)}</td>
                      <td className="py-2.5 px-5"><DirectionBadge direction={direction} /></td>
                      <td className="py-2.5 px-5">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold border ${CATEGORY_COLORS[category]}`}>
                          {category}
                        </span>
                      </td>
                      <td className="py-2.5 px-5">
                        <p className="font-medium text-white light:text-slate-900">{movementLabel(m)}</p>
                        {m.product_name && <p className="text-slate-500 text-[11px]">{m.product_name}</p>}
                        {m.note && <p className="text-slate-500 text-[11px]">{m.note}</p>}
                      </td>
                      <td className="py-2.5 px-5">
                        {ref ? (
                          <a
                            href={ref.href}
                            className="inline-flex items-center gap-1 font-mono text-[11px] px-2 py-0.5 rounded-full bg-orange-500/10 text-orange-400 border border-orange-500/20 hover:bg-orange-500/20 transition"
                          >
                            {ref.label}
                            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                          </a>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                      <td className="py-2.5 px-5"><CurrencyBadge m={m} /></td>
                      <td className={`py-2.5 px-5 text-right font-bold ${direction === "out" ? "text-rose-400" : "text-emerald-400"}`}>
                        {direction === "out" ? "-" : "+"}
                        {m.currency === "LIALCASH" ? lialCash(Math.abs(m.amount_cents)) : euro(Math.abs(m.amount_cents))}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="px-5 pb-4">
          <Pagination {...pagination} label="movimenti" />
        </div>
      </div>
    </div>
  );
}
