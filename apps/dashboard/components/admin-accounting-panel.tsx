"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { downloadCsv } from "@/lib/csv-export";
import {
  euro, formatDate, lialCash, movementCategory, movementDirection, movementLabel, movementSignedAmountCents,
  shortCode,
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

async function fetchAllMovements(): Promise<FinancialMovementRead[]> {
  const res = await fetch("/api/proxy/accounting/admin");
  if (!res.ok) throw new Error("Impossibile caricare la contabilità.");
  return res.json();
}

/** Admin-wide "Contabilità": every customer's LialCash + real-money
    movements in one place, filterable down to a single customer with
    their own totals -- the admin equivalent of accounting-panel.tsx (which
    only ever shows the caller's own). Same visual language (direction
    badge, currency/method badge, category pill) so a movement reads
    identically whether the customer or an admin is looking at it. */
export function AdminAccountingPanel() {
  const { data: movements, error } = useQuery({
    queryKey: ["admin", "accounting", "all"],
    queryFn: fetchAllMovements,
  });

  const [customerId, setCustomerId] = useState<string>("ALL");
  const [filter, setFilter] = useState<MovementFilter>("ALL");
  const [search, setSearch] = useState("");

  const list = useMemo(() => movements ?? [], [movements]);

  const customers = useMemo(() => {
    const byId = new Map<string, string>();
    for (const m of list) {
      if (m.customer_user_id && !byId.has(m.customer_user_id)) {
        byId.set(m.customer_user_id, m.customer_display_name ?? shortCode(m.customer_user_id));
      }
    }
    return Array.from(byId.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [list]);

  const matchesFilter = (m: FinancialMovementRead, f: MovementFilter) => {
    if (f === "ALL") return true;
    if (f === "LIALCASH") return m.currency === "LIALCASH";
    return m.currency === "EUR" && m.payment_method === f;
  };

  const normalizedSearch = search.trim().toLowerCase();
  const scopedList = customerId === "ALL" ? list : list.filter((m) => m.customer_user_id === customerId);
  const filteredList = scopedList.filter((m) => {
    if (!matchesFilter(m, filter)) return false;
    if (!normalizedSearch) return true;
    return (
      movementLabel(m).toLowerCase().includes(normalizedSearch) ||
      (m.product_name ?? "").toLowerCase().includes(normalizedSearch) ||
      (m.customer_display_name ?? "").toLowerCase().includes(normalizedSearch)
    );
  });

  const totalLialCashCents = scopedList.filter((m) => m.currency === "LIALCASH").reduce((sum, m) => sum + movementSignedAmountCents(m), 0);
  const totalBankTransferCents = scopedList
    .filter((m) => m.currency === "EUR" && m.payment_method === "BANK_TRANSFER")
    .reduce((sum, m) => sum + Math.abs(m.amount_cents), 0);
  const totalCardCents = scopedList
    .filter((m) => m.currency === "EUR" && m.payment_method === "CARD")
    .reduce((sum, m) => sum + Math.abs(m.amount_cents), 0);

  function handleExportCsv() {
    downloadCsv(
      `contabilita-admin-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Data", "Cliente", "Tipo", "Movimento", "Descrizione", "Valuta", "Metodo di pagamento", "Entrata/Uscita", "Importo", "Nota"],
      filteredList.map((m) => [
        formatDate(m.created_at),
        m.customer_display_name ?? "",
        movementCategory(m),
        movementLabel(m),
        m.product_name ?? "",
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
      <div>
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Contabilità</h3>
        <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
          Ogni movimento LialCash e ogni pagamento reale (carta o bonifico) di tutti i clienti, in un unico posto.
          Filtra per cliente per vedere il suo estratto conto personale.
        </p>
      </div>

      {/* Customer filter */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="space-y-1">
          <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Cliente</label>
          <select
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            className="w-full max-w-xs rounded-xl glass-input px-3 py-2 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
          >
            <option value="ALL">Tutti i clienti ({customers.length})</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1 flex-1 min-w-[200px]">
          <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Cerca</label>
          <div className="relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
            </svg>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Prodotto, cliente, tipo movimento..."
              className="w-full pl-9 pr-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 text-sm text-white light:text-slate-900 placeholder:text-slate-500 focus:outline-none focus:border-orange-500/50 transition"
            />
          </div>
        </div>
      </div>

      {/* Totals -- scoped to the selected customer, or org-wide when "Tutti" */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-gradient-to-br from-orange-500/10 to-transparent">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Saldo netto LialCash</p>
          <p className={`text-xl font-bold ${totalLialCashCents < 0 ? "text-rose-400" : "text-orange-400"}`}>
            {lialCash(totalLialCashCents)}
          </p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Incassato con Bonifico</p>
          <p className="text-xl font-bold text-white light:text-slate-900">{euro(totalBankTransferCents)}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Incassato con Carta (Stripe)</p>
          <p className="text-xl font-bold text-white light:text-slate-900">{euro(totalCardCents)}</p>
        </div>
      </div>

      {/* Filters + export */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {FILTER_TABS.map((tab) => {
            const count = scopedList.filter((m) => matchesFilter(m, tab.key)).length;
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
                {customerId === "ALL" && <th className="py-2 px-5">Cliente</th>}
                <th className="py-2 px-5">Tipo</th>
                <th className="py-2 px-5">Movimento</th>
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
                filteredList.map((m) => {
                  const direction = movementDirection(m);
                  const category = movementCategory(m);
                  return (
                    <tr key={m.id} className="text-slate-300 light:text-slate-600">
                      <td className="py-2.5 px-5 whitespace-nowrap text-slate-400 light:text-slate-500">{formatDate(m.created_at)}</td>
                      <td className="py-2.5 px-5"><DirectionBadge direction={direction} /></td>
                      {customerId === "ALL" && (
                        <td className="py-2.5 px-5">
                          <button
                            onClick={() => m.customer_user_id && setCustomerId(m.customer_user_id)}
                            className="font-medium text-white light:text-slate-900 hover:text-orange-400 transition cursor-pointer text-left"
                          >
                            {m.customer_display_name ?? "—"}
                          </button>
                        </td>
                      )}
                      <td className="py-2.5 px-5">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold border ${CATEGORY_COLORS[category]}`}>
                          {category}
                        </span>
                      </td>
                      <td className="py-2.5 px-5">
                        <p className="font-medium text-white light:text-slate-900">{movementLabel(m)}</p>
                        {m.product_name && <p className="text-slate-500 text-[11px]">{m.product_name}</p>}
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
      </div>
    </div>
  );
}
