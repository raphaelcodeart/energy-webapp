"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LialCashAmount } from "@/components/lial-cash-amount";
import { friendlyApiError } from "@/lib/api-error";
import {
  euro, formatDateTimeFull, movementDetailRef, movementDirection, movementLabel, movementsOfEntity,
} from "@/lib/accounting-format";
import type { AccountingDetailRead, FinancialMovementRead } from "@/lib/types";

const TONE_BADGE: Record<string, string> = {
  success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  warning: "bg-amber-500/10 text-amber-400 border-amber-500/25",
  danger: "bg-rose-500/10 text-rose-400 border-rose-500/25",
  neutral: "bg-slate-500/10 text-slate-400 border-slate-500/25",
};

const KIND_LABELS: Record<string, string> = {
  WALLET: "Movimento LialCash",
  ORDER: "Ordine",
  REDEMPTION: "Riscatto cashback",
  CONTRACT: "Contratto Lial Energy",
};

const TAB_LABELS: Record<string, string> = {
  orders: "Apri in I miei Ordini",
  cashback: "Apri in Riscatta Cashback",
  contracts: "Apri in I miei Contratti",
  wallet: "Apri il Wallet",
};

const INSTALMENT_STATUS: Record<string, { label: string; className: string }> = {
  PAID: { label: "Pagata", className: "text-emerald-400" },
  SCHEDULED: { label: "Prevista", className: "text-slate-400" },
  FAILED: { label: "Non addebitata", className: "text-rose-400" },
};

/** The detail of one movement -- or of the order, cashback redemption or
    contract it belongs to (Session 54).

    Everything is linked: a LialCash movement shows the order it paid, the
    order shows every movement it produced (card payment, LialCash used,
    cashback), and each of those opens in place, with "Indietro" to return.
    The timeline carries the exact time of every step and who did it --
    Stripe on its own, or the administrator who confirmed a transfer. */
export function AccountingDetailModal({
  initialRef,
  scope,
  movements,
  onClose,
  onOpenTab,
}: {
  initialRef: string;
  /** "mine" for the customer's own things, "admin" for the back office. */
  scope: "mine" | "admin";
  /** The list on screen, to show the movements tied to the opened thing. */
  movements: FinancialMovementRead[];
  onClose: () => void;
  onOpenTab?: (tab: string) => void;
}) {
  const [stack, setStack] = useState<string[]>([initialRef]);
  const ref = stack[stack.length - 1]!;
  const { data, error, isLoading } = useQuery<AccountingDetailRead>({
    queryKey: ["accounting", scope, "detail", ref],
    queryFn: async () => {
      const res = await fetch(`/api/proxy/accounting/${scope}/detail?ref=${encodeURIComponent(ref)}`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });

  function open(next: string) {
    if (next !== ref) setStack((s) => [...s, next]);
  }

  const linked = data
    ? movementsOfEntity(movements, data).filter((m) => movementDetailRef(m) !== ref || m.kind === "WALLET")
    : [];

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center sm:p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full sm:max-w-2xl max-h-[92vh] overflow-y-auto rounded-t-3xl sm:rounded-2xl border border-white/10 light:border-slate-200 bg-slate-950 light:bg-white shadow-2xl animate-scale-up"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-5 py-3 border-b border-white/10 light:border-slate-200 bg-slate-950/95 light:bg-white/95 backdrop-blur">
          <div className="flex items-center gap-2 min-w-0">
            {stack.length > 1 && (
              <button
                onClick={() => setStack((s) => s.slice(0, -1))}
                className="px-2.5 py-1 rounded-lg text-xs font-semibold text-slate-300 light:text-slate-600 hover:bg-white/10 light:hover:bg-slate-900/5 cursor-pointer"
              >
                ← Indietro
              </button>
            )}
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 truncate">
              {data ? KIND_LABELS[data.kind] : "Dettaglio"}
            </span>
          </div>
          <button onClick={onClose} aria-label="Chiudi" className="p-1.5 rounded-lg text-slate-400 hover:text-white light:hover:text-slate-900 hover:bg-white/10 cursor-pointer">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {isLoading && <div className="m-5 h-48 rounded-2xl bg-white/5 light:bg-slate-900/5 animate-pulse" />}
        {error && <p className="m-5 text-sm text-rose-400">{(error as Error).message}</p>}

        {data && (
          <div className="p-5 space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="text-xl font-bold text-white light:text-slate-900 leading-tight">{data.title}</h3>
                {data.subtitle && <p className="text-xs text-slate-400 light:text-slate-500 mt-1">{data.subtitle}</p>}
                {data.status && (
                  <span className={`inline-block mt-2 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${TONE_BADGE[data.status_tone]}`}>
                    {data.status}
                  </span>
                )}
              </div>
              {data.amount_cents != null && (
                <div className={`text-right text-2xl font-extrabold tabular-nums shrink-0 ${
                  data.direction === "in" ? "text-emerald-400" : "text-white light:text-slate-900"
                }`}>
                  {data.currency === "LIALCASH" ? (
                    <LialCashAmount cents={Math.abs(data.amount_cents)} sign={data.direction === "out" ? "-" : "+"} />
                  ) : (
                    euro(Math.abs(data.amount_cents))
                  )}
                </div>
              )}
            </div>

            {data.facts.length > 0 && (
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">Dettagli</h4>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 rounded-2xl border border-white/10 light:border-slate-200 px-4">
                  {data.facts.map((fact) => (
                    <div key={fact.label} className="py-2.5 border-b border-white/5 light:border-slate-100 min-w-0">
                      <dt className="text-[11px] text-slate-500">{fact.label}</dt>
                      <dd className={`text-sm font-semibold text-slate-100 light:text-slate-800 break-words ${fact.mono ? "font-mono text-xs" : ""}`}>
                        {fact.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}

            {data.timeline.length > 0 && (
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-3">Cronologia</h4>
                <ol className="relative ml-2 border-l border-white/10 light:border-slate-200 space-y-4">
                  {data.timeline.map((event, i) => (
                    <li key={`${event.label}-${i}`} className="ml-4">
                      <span
                        className={`absolute -left-[5px] mt-1.5 w-2.5 h-2.5 rounded-full ${
                          event.tone === "pending"
                            ? "bg-slate-600 ring-2 ring-slate-500/30"
                            : event.tone === "warning"
                              ? "bg-amber-400"
                              : "bg-emerald-400"
                        }`}
                      />
                      <p className={`text-sm font-semibold ${event.tone === "pending" ? "text-slate-400" : "text-white light:text-slate-900"}`}>
                        {event.label}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {event.at ? <span className="font-bold tabular-nums">{formatDateTimeFull(event.at)}</span> : "In attesa"}
                        {event.by && <> · {event.by}</>}
                      </p>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {data.instalments.length > 0 && (
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
                  {data.instalments.length === 1 ? "Pagamento" : `Rate (${data.instalments.filter((r) => r.status === "PAID").length}/${data.instalments.length} pagate)`}
                </h4>
                <div className="overflow-x-auto rounded-2xl border border-white/10 light:border-slate-200">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-slate-500 border-b border-white/10 light:border-slate-200">
                        <th className="py-2 px-3">#</th>
                        <th className="py-2 px-3">Prevista</th>
                        <th className="py-2 px-3 text-right">Importo</th>
                        <th className="py-2 px-3">Stato</th>
                        <th className="py-2 px-3">Incassata</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 light:divide-slate-100">
                      {data.instalments.map((row) => (
                        <tr key={row.number}>
                          <td className="py-2 px-3 font-bold text-slate-300 light:text-slate-600">{row.number}</td>
                          <td className="py-2 px-3 text-slate-400">{new Date(row.due_date).toLocaleDateString("it-IT")}</td>
                          <td className="py-2 px-3 text-right font-semibold text-white light:text-slate-900 tabular-nums">{euro(row.amount_cents)}</td>
                          <td className={`py-2 px-3 font-semibold ${INSTALMENT_STATUS[row.status]?.className ?? ""}`}>
                            {INSTALMENT_STATUS[row.status]?.label ?? row.status}
                          </td>
                          <td className="py-2 px-3 text-slate-400">
                            {row.paid_at ? (
                              <>
                                <span className="font-bold tabular-nums">{formatDateTimeFull(row.paid_at)}</span>
                                {row.source && <span className="block text-[10px]">{row.source}{row.confirmed_by ? ` · ${row.confirmed_by}` : ""}</span>}
                              </>
                            ) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {(linked.length > 0 || data.related_refs.length > 0) && (
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">Collegati</h4>
                <div className="space-y-1.5">
                  {data.related_refs.map((related) => (
                    <button
                      key={related}
                      onClick={() => open(related)}
                      className="w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl border border-orange-500/25 bg-orange-500/5 hover:bg-orange-500/10 text-left cursor-pointer"
                    >
                      <span className="text-sm font-semibold text-orange-300 light:text-orange-600">
                        {related.startsWith("order:") ? "Ordine" : related.startsWith("redemption:") ? "Riscatto cashback" : "Contratto"} #
                        {related.split(":")[1]!.slice(0, 8).toUpperCase()}
                      </span>
                      <span className="text-orange-400">→</span>
                    </button>
                  ))}
                  {linked.map((m) => {
                    const target = movementDetailRef(m);
                    const out = movementDirection(m) === "out";
                    return (
                      <button
                        key={m.id}
                        onClick={() => target && open(target)}
                        disabled={!target || target === ref}
                        className="w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl border border-white/10 light:border-slate-200 hover:bg-white/5 light:hover:bg-slate-50 text-left cursor-pointer disabled:cursor-default"
                      >
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-white light:text-slate-900 truncate">{movementLabel(m)}</span>
                          <span className="block text-[11px] text-slate-500 font-bold tabular-nums">{formatDateTimeFull(m.created_at)}</span>
                        </span>
                        <span className={`text-sm font-bold tabular-nums shrink-0 ${out ? "text-rose-400" : "text-emerald-400"}`}>
                          {m.currency === "LIALCASH" ? (
                            <LialCashAmount cents={Math.abs(m.amount_cents)} sign={out ? "-" : "+"} />
                          ) : (
                            `${out ? "-" : "+"}${euro(Math.abs(m.amount_cents))}`
                          )}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            )}

            {onOpenTab && data.tab && (
              <button
                onClick={() => onOpenTab(data.tab!)}
                className="w-full rounded-xl bg-white/10 light:bg-slate-900/5 hover:bg-white/20 light:hover:bg-slate-900/10 py-2.5 text-xs font-semibold text-white light:text-slate-700 cursor-pointer"
              >
                {TAB_LABELS[data.tab]}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
