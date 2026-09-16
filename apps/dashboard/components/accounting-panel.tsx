"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AccountingDetailModal } from "@/components/accounting-detail-modal";
import { LialCashAmount } from "@/components/lial-cash-amount";
import { Pagination, usePagination } from "@/components/pagination";
import {
  euro, formatDate, formatDayShort, formatTime, lialCash, monthKey, monthLabel, movementCategory,
  movementDetailRef, movementDirection, movementEntity, movementLabel, movementReferenceLink,
} from "@/lib/accounting-format";
import { downloadCsv } from "@/lib/csv-export";
import type { AccountingSummaryRead, FinancialMovementRead } from "@/lib/types";

type Filter = "ALL" | "PAYMENTS" | "CONTRACTS" | "CASHBACK" | "LIALCASH" | "CARD" | "BANK_TRANSFER" | "IN" | "OUT";

const FILTERS: { key: Filter; label: string; match: (m: FinancialMovementRead) => boolean }[] = [
  { key: "ALL", label: "Tutti", match: () => true },
  { key: "PAYMENTS", label: "Pagamenti", match: (m) => m.currency === "EUR" },
  { key: "CONTRACTS", label: "Contratti", match: (m) => Boolean(m.contract_id) },
  { key: "CASHBACK", label: "Cashback", match: (m) => movementCategory(m) === "Cashback" },
  { key: "LIALCASH", label: "LialCash", match: (m) => m.currency === "LIALCASH" },
  { key: "CARD", label: "Carta", match: (m) => m.payment_method === "CARD" },
  { key: "BANK_TRANSFER", label: "Bonifico", match: (m) => m.payment_method === "BANK_TRANSFER" },
  { key: "IN", label: "Entrate", match: (m) => movementDirection(m) === "in" },
  { key: "OUT", label: "Uscite", match: (m) => movementDirection(m) === "out" },
];

const CATEGORY_STYLE: Record<string, { tile: string; icon: string }> = {
  Pagamento: { tile: "bg-violet-500/15 text-violet-400", icon: "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" },
  Contratto: { tile: "bg-amber-500/15 text-amber-400", icon: "M13 10V3L4 14h7v7l9-11h-7z" },
  Cashback: { tile: "bg-emerald-500/15 text-emerald-400", icon: "M9 14l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" },
  Ricarica: { tile: "bg-sky-500/15 text-sky-400", icon: "M12 4v16m8-8H4" },
  Trasferimento: { tile: "bg-cyan-500/15 text-cyan-400", icon: "M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" },
  Storno: { tile: "bg-slate-500/15 text-slate-400", icon: "M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" },
  Altro: { tile: "bg-slate-500/15 text-slate-400", icon: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" },
};

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error("Impossibile caricare la contabilità.");
  return res.json();
}

function Kpi({
  label,
  value,
  hint,
  accent = "neutral",
  big = false,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  accent?: "orange" | "emerald" | "violet" | "sky" | "neutral";
  big?: boolean;
}) {
  const accents: Record<string, string> = {
    orange: "from-orange-500/15 border-orange-500/20",
    emerald: "from-emerald-500/15 border-emerald-500/20",
    violet: "from-violet-500/15 border-violet-500/20",
    sky: "from-sky-500/15 border-sky-500/20",
    neutral: "from-white/[0.03] border-white/10 light:border-slate-200",
  };
  return (
    <div className={`rounded-2xl border bg-gradient-to-br to-transparent p-4 ${accents[accent]} light:bg-white`}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <div className={`mt-1 font-extrabold tabular-nums text-white light:text-slate-900 ${big ? "text-2xl" : "text-lg"}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-slate-500 leading-snug">{hint}</div>}
    </div>
  );
}

/** "Contabilità" -- the customer's own money, in one place (redesigned in
    Session 54).

    At the top, totals computed by the server (what was paid, how, LialCash,
    contracts, and commissions for someone who is also a promoter). Below,
    every movement grouped by month, searchable by text, type and dates.
    Every row opens its detail, and every order / cashback redemption /
    contract chip opens that thing with all of its movements -- so each euro
    and each LialCash can be followed back to where it came from. */
export function AccountingPanel({ onOpenTab }: { onOpenTab?: (tab: string) => void }) {
  const { data: movements, error } = useQuery({
    queryKey: ["accounting", "mine"],
    queryFn: () => fetchJson<FinancialMovementRead[]>("/api/proxy/accounting/mine"),
    refetchOnWindowFocus: true,
  });
  const { data: summary } = useQuery({
    queryKey: ["accounting", "mine", "summary"],
    queryFn: () => fetchJson<AccountingSummaryRead>("/api/proxy/accounting/mine/summary"),
    refetchOnWindowFocus: true,
  });
  const [filter, setFilter] = useState<Filter>("ALL");
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [detailRef, setDetailRef] = useState<string | null>(null);

  const list = movements ?? [];
  const needle = search.trim().toLowerCase();
  const active = FILTERS.find((f) => f.key === filter)!;
  const filtered = list.filter((m) => {
    if (!active.match(m)) return false;
    const day = m.created_at.slice(0, 10);
    if (from && day < from) return false;
    if (to && day > to) return false;
    if (!needle) return true;
    const amount = (Math.abs(m.amount_cents) / 100).toFixed(2);
    return [movementLabel(m), m.product_name, m.note, movementEntity(m)?.label, amount, amount.replace(".", ",")]
      .filter(Boolean)
      .some((v) => v!.toLowerCase().includes(needle));
  });
  const pagination = usePagination(filtered, 25);

  const outEur = filtered.filter((m) => m.currency === "EUR").reduce((s, m) => s + Math.abs(m.amount_cents), 0);
  const inLialCash = filtered
    .filter((m) => m.currency === "LIALCASH" && m.amount_cents > 0)
    .reduce((s, m) => s + m.amount_cents, 0);
  const filtersActive = Boolean(filter !== "ALL" || needle || from || to);

  const groups: { key: string; rows: FinancialMovementRead[] }[] = [];
  for (const m of pagination.pageItems) {
    const key = monthKey(m.created_at);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.rows.push(m);
    else groups.push({ key, rows: [m] });
  }

  function exportCsv() {
    downloadCsv(
      `contabilita-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Data", "Tipo", "Movimento", "Descrizione", "Riferimento", "Valuta", "Metodo di pagamento", "Entrata/Uscita", "Importo", "Nota"],
      filtered.map((m) => [
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

  if (error) return <p className="text-sm text-rose-400">Impossibile caricare la contabilità.</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-white light:text-slate-900">Contabilità</h2>
          <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
            Ogni euro pagato e ogni LialCash, con il dettaglio di ciascun movimento.
          </p>
        </div>
        <button
          onClick={exportCsv}
          disabled={filtered.length === 0}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10 light:hover:bg-slate-900/5 cursor-pointer disabled:opacity-40"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Esporta CSV
        </button>
      </div>

      {!summary ? (
        <div className="h-40 rounded-2xl bg-white/5 light:bg-slate-900/5 animate-pulse" />
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Kpi
              big
              accent="violet"
              label="Totale speso"
              value={euro(summary.spent_total_cents)}
              hint={`${summary.payments_count} pagamenti · carta ${euro(summary.spent_card_cents)} · bonifico ${euro(summary.spent_bank_transfer_cents)}`}
            />
            <Kpi big label="Speso questo mese" value={euro(summary.spent_this_month_cents)} />
            <Kpi
              big
              accent="orange"
              label="Saldo LialCash"
              value={<LialCashAmount cents={summary.lialcash_balance_cents} align="left" />}
            />
            <Kpi
              big
              accent="emerald"
              label="Cashback ricevuto"
              value={<LialCashAmount cents={summary.cashback_received_cents} align="left" />}
            />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <Kpi accent="sky" label="Pagato con carta" value={euro(summary.spent_card_cents)} hint="Stripe" />
            <Kpi accent="sky" label="Pagato con bonifico" value={euro(summary.spent_bank_transfer_cents)} />
            <Kpi
              label="Contratti"
              value={euro(summary.spent_contracts_cents)}
              hint={
                <>
                  {summary.contracts_active} attivi · {summary.instalments_paid} rate pagate
                  {summary.next_instalment_due_date && summary.next_instalment_cents != null && (
                    <span className="block text-amber-400">
                      Prossima: {euro(summary.next_instalment_cents)} il{" "}
                      {new Date(summary.next_instalment_due_date).toLocaleDateString("it-IT")}
                    </span>
                  )}
                </>
              }
            />
            <Kpi
              label="Shop e riscatti"
              value={euro(summary.spent_orders_cents + summary.spent_redemptions_cents)}
              hint={`ordini ${euro(summary.spent_orders_cents)} · riscatti ${euro(summary.spent_redemptions_cents)}`}
            />
            <Kpi
              label="LialCash ricevuti"
              value={lialCash(summary.lialcash_received_cents)}
              hint={`spesi ${lialCash(summary.lialcash_spent_cents)}`}
            />
            {summary.commissions_total_cents != null ? (
              <Kpi
                accent="emerald"
                label="Provvigioni maturate"
                value={euro(summary.commissions_total_cents)}
                hint={`da incassare ${euro(summary.commissions_to_collect_cents ?? 0)} · pagate ${euro(summary.commissions_paid_cents ?? 0)}`}
              />
            ) : (
              <Kpi label="Movimenti totali" value={list.length} hint="LialCash e pagamenti" />
            )}
          </div>
        </div>
      )}

      <div className="rounded-2xl border border-white/10 light:border-slate-200 bg-slate-950/40 light:bg-white p-3 sm:p-4 space-y-3">
        <div className="flex flex-col lg:flex-row gap-2">
          <div className="relative flex-1">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
            </svg>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cerca per descrizione, prodotto, importo, n° ordine / riscatto / contratto…"
              className="w-full rounded-xl glass-input pl-9 pr-3 py-2.5 text-sm focus:border-orange-500"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-[10px] font-bold uppercase text-slate-500">Dal</label>
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded-xl glass-input px-2.5 py-2 text-xs" />
            <label className="text-[10px] font-bold uppercase text-slate-500">al</label>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded-xl glass-input px-2.5 py-2 text-xs" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold transition cursor-pointer ${
                filter === f.key
                  ? "bg-orange-600 text-white"
                  : "bg-white/5 light:bg-slate-900/5 text-slate-400 light:text-slate-600 hover:bg-white/10"
              }`}
            >
              {f.label}
              <span className="ml-1 opacity-60">{list.filter(f.match).length}</span>
            </button>
          ))}
          {filtersActive && (
            <button
              onClick={() => { setFilter("ALL"); setSearch(""); setFrom(""); setTo(""); }}
              className="ml-auto text-[11px] font-semibold text-orange-400 hover:text-orange-300 cursor-pointer"
            >
              Azzera filtri
            </button>
          )}
        </div>
        {filtersActive && (
          <p className="text-[11px] text-slate-400 light:text-slate-500">
            <strong className="text-slate-200 light:text-slate-800">{filtered.length}</strong> movimenti · pagati{" "}
            <strong className="text-slate-200 light:text-slate-800">{euro(outEur)}</strong> · LialCash ricevuti{" "}
            <strong className="text-slate-200 light:text-slate-800">{lialCash(inLialCash)}</strong>
          </p>
        )}
      </div>

      {movements === undefined ? (
        <div className="h-64 rounded-2xl bg-white/5 light:bg-slate-900/5 animate-pulse" />
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-white/10 light:border-slate-200 p-10 text-center text-sm text-slate-500">
          Nessun movimento corrisponde alla ricerca.
        </div>
      ) : (
        <div className="space-y-5">
          {groups.map((group) => {
            const spent = group.rows.filter((m) => m.currency === "EUR").reduce((s, m) => s + Math.abs(m.amount_cents), 0);
            return (
              <section key={group.key}>
                <div className="flex items-baseline justify-between px-1 mb-2">
                  <h3 className="text-sm font-bold text-white light:text-slate-900">{monthLabel(group.key)}</h3>
                  {spent > 0 && (
                    <span className="text-[11px] text-slate-500">
                      pagati <strong className="text-slate-300 light:text-slate-700">{euro(spent)}</strong>
                    </span>
                  )}
                </div>
                <div className="rounded-2xl border border-white/10 light:border-slate-200 bg-slate-950/40 light:bg-white divide-y divide-white/5 light:divide-slate-100 overflow-hidden">
                  {group.rows.map((m) => (
                    <MovementRow key={m.id} m={m} onOpen={setDetailRef} />
                  ))}
                </div>
              </section>
            );
          })}
          <Pagination {...pagination} label="movimenti" />
        </div>
      )}

      {detailRef && (
        <AccountingDetailModal
          initialRef={detailRef}
          scope="mine"
          movements={list}
          onClose={() => setDetailRef(null)}
          onOpenTab={
            onOpenTab
              ? (tab) => {
                  setDetailRef(null);
                  onOpenTab(tab);
                }
              : undefined
          }
        />
      )}
    </div>
  );
}

function MovementRow({ m, onOpen }: { m: FinancialMovementRead; onOpen: (ref: string) => void }) {
  const direction = movementDirection(m);
  const category = movementCategory(m);
  const style = CATEGORY_STYLE[category] ?? CATEGORY_STYLE.Altro!;
  const entity = movementEntity(m);
  const detail = movementDetailRef(m);
  const out = direction === "out";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => detail && onOpen(detail)}
      onKeyDown={(e) => e.key === "Enter" && detail && onOpen(detail)}
      className="group flex items-center gap-3 sm:gap-4 px-3 sm:px-4 py-3 hover:bg-white/[0.03] light:hover:bg-slate-50 cursor-pointer transition"
    >
      <div className="hidden sm:block w-12 shrink-0 text-center">
        <p className="text-[11px] font-extrabold uppercase text-slate-300 light:text-slate-700 leading-tight">{formatDayShort(m.created_at)}</p>
        <p className="text-[10px] font-semibold text-slate-500 tabular-nums">{formatTime(m.created_at)}</p>
      </div>
      <span className={`flex items-center justify-center w-10 h-10 rounded-xl shrink-0 ${style.tile}`}>
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={style.icon} />
        </svg>
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-semibold text-white light:text-slate-900 leading-snug truncate">{movementLabel(m)}</p>
        <p className="text-[11px] text-slate-500 truncate">
          <span className="sm:hidden font-bold text-slate-400">
            {formatDayShort(m.created_at)} {formatTime(m.created_at)} ·{" "}
          </span>
          {[m.product_name, m.kind === "WALLET" ? m.note : null].filter(Boolean).join(" · ") || category}
        </p>
        {entity && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpen(entity.ref);
            }}
            className="mt-1 inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-orange-500/10 border border-orange-500/20 text-[10px] font-bold text-orange-400 hover:bg-orange-500/20 cursor-pointer"
          >
            {entity.label} →
          </button>
        )}
      </div>
      <div className="text-right shrink-0">
        <div className={`text-base sm:text-lg font-extrabold tabular-nums ${out ? "text-white light:text-slate-900" : "text-emerald-400"}`}>
          {m.currency === "LIALCASH" ? (
            <LialCashAmount cents={Math.abs(m.amount_cents)} sign={out ? "-" : "+"} />
          ) : (
            `${out ? "-" : "+"}${euro(Math.abs(m.amount_cents))}`
          )}
        </div>
        {m.currency === "EUR" && (
          <p className="text-[10px] font-semibold text-slate-500">
            {m.payment_method === "CARD" ? "Carta · Stripe" : m.payment_method === "BANK_TRANSFER" ? "Bonifico" : "Euro"}
          </p>
        )}
      </div>
      <svg className="hidden sm:block w-4 h-4 text-slate-600 group-hover:text-orange-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
      </svg>
    </div>
  );
}
