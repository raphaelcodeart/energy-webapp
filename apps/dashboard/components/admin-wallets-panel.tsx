"use client";

import { Fragment, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { WalletAdminListItemRead, WalletTransactionRead } from "@/lib/types";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";

const TYPE_LABELS: Record<string, string> = {
  ADMIN_CREDIT: "Ricarica/Cashback",
  TRANSFER: "Trasferimento",
  PURCHASE_DEBIT: "Pagamento ordine (crediti)",
  REVERSAL: "Storno",
};

const TYPE_COLORS: Record<string, string> = {
  ADMIN_CREDIT: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  TRANSFER: "bg-sky-500/10 text-sky-400 border-sky-500/20",
  PURCHASE_DEBIT: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  REVERSAL: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};

// Finer-grained label than TYPE_LABELS alone -- distinguishes a plain admin
// top-up from the two lines a partner-invoice redemption always writes
// together (see docs/cashback-partner-invoices-plan.md), without needing to
// read the free-text note.
const SOURCE_LABELS: Record<string, string> = {
  MANUAL_ADMIN: "Ricarica manuale",
  INVOICE_REDEMPTION_BASE: "Riscatto fattura",
  INVOICE_REDEMPTION_BONUS: "Bonus 3% riscatto fattura",
};

function transactionLabel(t: { type: string; source: string | null }): string {
  const sourceLabel = t.source ? SOURCE_LABELS[t.source] : undefined;
  return sourceLabel ?? TYPE_LABELS[t.type] ?? t.type;
}

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

async function fetchWallets(): Promise<WalletAdminListItemRead[]> {
  const res = await fetch("/api/proxy/wallets/admin");
  if (!res.ok) throw new Error("Impossibile caricare i wallet.");
  return res.json();
}

async function fetchTransactions(type?: string): Promise<WalletTransactionRead[]> {
  const search = new URLSearchParams();
  if (type && type !== "ALL") search.set("type", type);
  const qs = search.toString();
  const res = await fetch(`/api/proxy/wallets/admin/transactions${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error("Impossibile caricare le transazioni.");
  return res.json();
}

export function AdminWalletsPanel() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reversingId, setReversingId] = useState<string | null>(null);
  const [reverseError, setReverseError] = useState<string | null>(null);
  const [topUpForUserId, setTopUpForUserId] = useState<string | null>(null);
  const [topUpAmount, setTopUpAmount] = useState("");
  const [topUpNote, setTopUpNote] = useState("");
  const [topUpLoading, setTopUpLoading] = useState(false);
  const [topUpError, setTopUpError] = useState<string | null>(null);

  const { data: wallets, error: walletsError } = useQuery({
    queryKey: ["admin", "wallets", "all"],
    queryFn: fetchWallets,
  });
  const { data: transactions, error: transactionsError, isLoading } = useQuery({
    queryKey: ["admin", "wallets", "transactions", typeFilter],
    queryFn: () => fetchTransactions(typeFilter),
  });

  const filteredWallets = (wallets ?? []).filter(
    (w) =>
      w.owner_display_name.toLowerCase().includes(search.toLowerCase()) ||
      w.owner_email.toLowerCase().includes(search.toLowerCase()) ||
      w.address.toLowerCase().includes(search.toLowerCase())
  );

  const totalBalance = (wallets ?? []).reduce((sum, w) => sum + w.balance_cents, 0);
  const totalCredited = (transactions ?? [])
    .filter((t) => t.type === "ADMIN_CREDIT")
    .reduce((sum, t) => sum + t.amount_cents, 0);

  async function handleReverse(transactionId: string) {
    const reason = window.prompt("Motivo dello storno:");
    if (!reason) return;
    setReversingId(transactionId);
    setReverseError(null);
    try {
      const res = await fetch(`/api/proxy/wallets/admin/transactions/${transactionId}/reverse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason, idempotency_key: crypto.randomUUID() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
    } catch (err: any) {
      setReverseError(err.message || "Impossibile stornare la transazione.");
    } finally {
      setReversingId(null);
    }
  }

  function openTopUp(userId: string) {
    setTopUpForUserId(topUpForUserId === userId ? null : userId);
    setTopUpAmount("");
    setTopUpNote("");
    setTopUpError(null);
  }

  async function handleTopUp(e: React.FormEvent, userId: string) {
    e.preventDefault();
    const amountCents = Math.round(parseFloat(topUpAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setTopUpError("Inserisci un importo valido.");
      return;
    }
    setTopUpLoading(true);
    setTopUpError(null);
    try {
      const res = await fetch("/api/proxy/wallets/admin/topup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          amount_cents: amountCents,
          note: topUpNote || null,
          idempotency_key: crypto.randomUUID(),
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setTopUpForUserId(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
    } catch (err: any) {
      setTopUpError(err.message || "Impossibile ricaricare il wallet.");
    } finally {
      setTopUpLoading(false);
    }
  }

  function handleExportCsv() {
    downloadCsv(
      `wallet_transazioni_${new Date().toISOString().slice(0, 10)}`,
      ["ID", "Tipo", "Da", "A", "Importo (EUR)", "Nota", "Data"],
      (transactions ?? []).map((t) => [
        t.id, transactionLabel(t), t.from_display_name ?? "Sistema", t.to_display_name ?? "Sistema",
        (t.amount_cents / 100).toFixed(2), t.note ?? "", t.created_at,
      ])
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI */}
      <div className="grid grid-cols-2 gap-4">
        <div className="glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Saldo totale wallet</p>
          <p className="text-xl font-bold text-white light:text-slate-900">{euro(totalBalance)}</p>
        </div>
        <div className="glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Totale ricaricato (nel filtro)</p>
          <p className="text-xl font-bold text-emerald-400">{euro(totalCredited)}</p>
        </div>
      </div>

      {/* Wallet balances */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="p-5 pb-3 flex items-center justify-between gap-4">
          <h3 className="text-sm font-semibold text-white light:text-slate-900">Saldi per utente</h3>
          <input
            type="text"
            placeholder="Cerca per nome, email o indirizzo..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-xl glass-input px-3 py-1.5 text-xs max-w-xs focus:border-orange-500"
          />
        </div>
        {walletsError && <p className="px-5 pb-3 text-sm text-rose-400">Impossibile caricare i wallet.</p>}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 px-5">Utente</th>
                <th className="py-2 px-5">Ruoli</th>
                <th className="py-2 px-5">Indirizzo</th>
                <th className="py-2 px-5 text-right">Saldo</th>
                <th className="py-2 px-5 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {wallets === undefined ? (
                <tr><td colSpan={5} className="text-center py-6 text-slate-500">Caricamento...</td></tr>
              ) : filteredWallets.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-6 text-slate-500">Nessun wallet trovato.</td></tr>
              ) : (
                filteredWallets.map((w) => (
                  <Fragment key={w.id}>
                    <tr className="text-slate-300 light:text-slate-600">
                      <td className="py-2 px-5">
                        <div className="font-medium text-white light:text-slate-900">{w.owner_display_name}</div>
                        <div className="text-[10px] text-slate-500">{w.owner_email}</div>
                      </td>
                      <td className="py-2 px-5">{w.owner_roles.join(", ") || "—"}</td>
                      <td className="py-2 px-5 font-mono text-[10px]">{w.address}</td>
                      <td className="py-2 px-5 text-right font-semibold text-orange-400">{euro(w.balance_cents)}</td>
                      <td className="py-2 px-5 text-right">
                        <button
                          onClick={() => openTopUp(w.user_id)}
                          className="px-2.5 py-1 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-[11px] font-semibold transition cursor-pointer"
                        >
                          {topUpForUserId === w.user_id ? "Annulla" : "Ricarica"}
                        </button>
                      </td>
                    </tr>
                    {topUpForUserId === w.user_id && (
                      <tr className="bg-white/2 light:bg-slate-900/[0.02]">
                        <td colSpan={5} className="px-5 py-3">
                          <form onSubmit={(e) => handleTopUp(e, w.user_id)} className="flex items-end gap-2">
                            <div className="space-y-1 flex-1 max-w-[160px]">
                              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Importo (EUR)</label>
                              <input
                                required
                                autoFocus
                                inputMode="decimal"
                                value={topUpAmount}
                                onChange={(e) => setTopUpAmount(e.target.value)}
                                placeholder="0,00"
                                className="w-full rounded-lg glass-input px-3 py-1.5 text-sm focus:border-orange-500"
                              />
                            </div>
                            <div className="space-y-1 flex-1">
                              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Nota (opzionale)</label>
                              <input
                                value={topUpNote}
                                onChange={(e) => setTopUpNote(e.target.value)}
                                placeholder="Cashback ordine..."
                                className="w-full rounded-lg glass-input px-3 py-1.5 text-sm focus:border-orange-500"
                              />
                            </div>
                            <button type="submit" disabled={topUpLoading}
                              className="px-4 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50 shrink-0">
                              {topUpLoading ? "..." : "Conferma"}
                            </button>
                          </form>
                          {topUpError && (
                            <div className="mt-2 p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{topUpError}</div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Filters + export */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
        >
          <option value="ALL">Tutti i tipi</option>
          <option value="ADMIN_CREDIT">Solo ricariche/cashback</option>
          <option value="TRANSFER">Solo trasferimenti</option>
          <option value="REVERSAL">Solo storni</option>
        </select>
        <button
          onClick={handleExportCsv}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Esporta CSV
        </button>
      </div>

      {reverseError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{reverseError}</div>
      )}
      {transactionsError && <p className="text-sm text-rose-400">Impossibile caricare le transazioni.</p>}

      {/* Global transaction ledger */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-3 px-5">Da</th>
                <th className="py-3 px-5">A</th>
                <th className="py-3 px-5">Tipo</th>
                <th className="py-3 px-5 text-right">Importo</th>
                <th className="py-3 px-5">Data</th>
                <th className="py-3 px-5 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {isLoading && (
                <tr><td colSpan={6} className="text-center py-8 text-slate-500">Caricamento...</td></tr>
              )}
              {!isLoading && (transactions ?? []).length === 0 && (
                <tr><td colSpan={6} className="text-center py-8 text-slate-500">Nessuna transazione.</td></tr>
              )}
              {(transactions ?? []).map((t) => (
                <Fragment key={t.id}>
                  <tr
                    className="text-slate-300 light:text-slate-600 hover:bg-white/5 transition-colors cursor-pointer"
                    onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                  >
                    <td className="py-3 px-5">{t.from_display_name ?? "Sistema"}</td>
                    <td className="py-3 px-5">{t.to_display_name ?? "Sistema"}</td>
                    <td className="py-3 px-5">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${TYPE_COLORS[t.type] ?? ""}`}>
                        {transactionLabel(t)}
                      </span>
                    </td>
                    <td className="py-3 px-5 text-right font-semibold text-orange-400">{euro(t.amount_cents)}</td>
                    <td className="py-3 px-5">{new Date(t.created_at).toLocaleString("it-IT")}</td>
                    <td className="py-3 px-5 text-right">
                      {t.type !== "REVERSAL" && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleReverse(t.id); }}
                          disabled={reversingId === t.id}
                          className="px-2.5 py-1 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                        >
                          {reversingId === t.id ? "..." : "Storna"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedId === t.id && (
                    <tr className="bg-white/2 light:bg-slate-900/[0.02]">
                      <td colSpan={6} className="px-5 py-4 text-xs space-y-1.5">
                        {t.note && <p><span className="text-slate-500">Nota:</span> <span className="text-slate-300 light:text-slate-600">{t.note}</span></p>}
                        {t.reference_contract_id && (
                          <p><span className="text-slate-500">Contratto collegato:</span> <span className="font-mono text-[10px] text-slate-300 light:text-slate-600">{t.reference_contract_id}</span></p>
                        )}
                        {t.from_address && <p><span className="text-slate-500">Indirizzo mittente:</span> <span className="font-mono text-[10px] text-slate-300 light:text-slate-600">{t.from_address}</span></p>}
                        {t.to_address && <p><span className="text-slate-500">Indirizzo destinatario:</span> <span className="font-mono text-[10px] text-slate-300 light:text-slate-600">{t.to_address}</span></p>}
                        <p className="font-mono text-[10px] text-slate-500">{t.id}</p>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
