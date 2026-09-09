"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { downloadCsv } from "@/lib/csv-export";
import type { FinancialMovementRead } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  ADMIN_CREDIT: "Ricarica/Cashback",
  TRANSFER: "Trasferimento",
  PURCHASE_DEBIT: "Pagamento ordine (LialCash)",
  REVERSAL: "Storno",
};

const SOURCE_LABELS: Record<string, string> = {
  MANUAL_ADMIN: "Ricarica manuale",
  INVOICE_REDEMPTION_BASE: "Riscatto fattura",
  INVOICE_REDEMPTION_BONUS: "Bonus 5% riscatto fattura",
  ORDER_CASHBACK_BASE: "Cashback ordine",
  ORDER_CASHBACK_BONUS: "Bonus 5% cashback ordine",
};

const PAYMENT_METHOD_LABELS: Record<string, string> = {
  BANK_TRANSFER: "Bonifico",
  CARD: "Carta (Stripe)",
};

type MovementFilter = "ALL" | "LIALCASH" | "BANK_TRANSFER" | "CARD";

const FILTER_TABS: { key: MovementFilter; label: string }[] = [
  { key: "ALL", label: "Tutte" },
  { key: "LIALCASH", label: "LialCash" },
  { key: "BANK_TRANSFER", label: "Bonifico" },
  { key: "CARD", label: "Carta" },
];

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// LialCash is Lial Energy's internal wallet credit, never plain EUR -- see
// wallet-panel.tsx's identical helper. Real-money movements (Stripe,
// bonifico) always stay euro().
function lialCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} LialCash`;
}

function movementLabel(m: FinancialMovementRead): string {
  if (m.kind === "ORDER_PAYMENT") {
    return m.payment_method ? PAYMENT_METHOD_LABELS[m.payment_method] ?? m.payment_method : "Pagamento ordine";
  }
  const sourceLabel = m.source ? SOURCE_LABELS[m.source] : undefined;
  return sourceLabel ?? (m.type ? TYPE_LABELS[m.type] ?? m.type : "Movimento wallet");
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { dateStyle: "medium", timeStyle: "short" });
}

function shortCode(id: string): string {
  return id.slice(0, 8).toUpperCase();
}

/** Every movement carries order_id or invoice_redemption_id when it's tied
    to one (a cashback credit, a purchase debit, the order's own real-money
    payment leg, or an invoice-redemption credit) -- shown as a clickable
    chip so a customer can always trace a LialCash movement back to
    exactly what generated it, not just the product/partner name. */
function referenceLink(m: FinancialMovementRead): { label: string; href: string } | null {
  if (m.order_id) return { label: `Ordine #${shortCode(m.order_id)}`, href: "/customer?tab=orders" };
  if (m.invoice_redemption_id) return { label: `Riscatto #${shortCode(m.invoice_redemption_id)}`, href: "/customer?tab=cashback" };
  return null;
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
    return m.kind === "ORDER_PAYMENT" && m.payment_method === f;
  };

  const filteredList = list.filter((m) => matchesFilter(m, filter));

  // Totals: LialCash net movement (can be negative -- a wallet spent more
  // than it received), plus separate EUR totals per real-money payment
  // method (an ORDER_PAYMENT amount_cents is always positive, see
  // accounting/service.py::list_my_movements).
  const totalLialCashCents = list.filter((m) => m.currency === "LIALCASH").reduce((sum, m) => sum + m.amount_cents, 0);
  const totalBankTransferCents = list
    .filter((m) => m.kind === "ORDER_PAYMENT" && m.payment_method === "BANK_TRANSFER")
    .reduce((sum, m) => sum + m.amount_cents, 0);
  const totalCardCents = list
    .filter((m) => m.kind === "ORDER_PAYMENT" && m.payment_method === "CARD")
    .reduce((sum, m) => sum + m.amount_cents, 0);

  function handleExportCsv() {
    downloadCsv(
      `contabilita-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Data", "Movimento", "Prodotto", "Riferimento", "Importo", "Valuta", "Metodo di pagamento", "Nota"],
      filteredList.map((m) => [
        formatDate(m.created_at),
        movementLabel(m),
        m.product_name ?? "",
        referenceLink(m)?.label ?? "",
        (m.amount_cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        m.currency === "LIALCASH" ? "LialCash" : "EUR",
        m.payment_method ? PAYMENT_METHOD_LABELS[m.payment_method] ?? m.payment_method : "",
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
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Totale LialCash</p>
          <p className={`text-xl font-bold ${totalLialCashCents < 0 ? "text-rose-400" : "text-orange-400"}`}>
            {lialCash(totalLialCashCents)}
          </p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Totale Bonifico</p>
          <p className="text-xl font-bold text-white light:text-slate-900">{euro(totalBankTransferCents)}</p>
        </div>
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Totale Carta (Stripe)</p>
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

      {/* Movements table */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 px-5">Data</th>
                <th className="py-2 px-5">Movimento</th>
                <th className="py-2 px-5">Prodotto</th>
                <th className="py-2 px-5">Riferimento</th>
                <th className="py-2 px-5">Nota</th>
                <th className="py-2 px-5 text-right">Importo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {movements === undefined ? (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">Caricamento...</td></tr>
              ) : filteredList.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">Nessuna transazione in questa categoria.</td></tr>
              ) : (
                filteredList.map((m) => {
                  const isNegative = m.amount_cents < 0;
                  return (
                    <tr key={m.id} className="text-slate-300 light:text-slate-600">
                      <td className="py-2 px-5 whitespace-nowrap">{formatDate(m.created_at)}</td>
                      <td className="py-2 px-5">
                        {movementLabel(m)}
                        <span className={`ml-2 inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold border ${
                          m.currency === "LIALCASH"
                            ? "bg-orange-500/10 text-orange-400 border-orange-500/20"
                            : "bg-sky-500/10 text-sky-400 border-sky-500/20"
                        }`}>
                          {m.currency === "LIALCASH" ? "LialCash" : "EUR"}
                        </span>
                      </td>
                      <td className="py-2 px-5 text-slate-400 light:text-slate-500">{m.product_name ?? "—"}</td>
                      <td className="py-2 px-5">
                        {(() => {
                          const ref = referenceLink(m);
                          return ref ? (
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
                          );
                        })()}
                      </td>
                      <td className="py-2 px-5 text-slate-500">{m.note ?? "—"}</td>
                      <td className={`py-2 px-5 text-right font-semibold ${isNegative ? "text-rose-400" : "text-emerald-400"}`}>
                        {isNegative ? "-" : "+"}
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
