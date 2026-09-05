"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { WalletRead, WalletTransactionRead } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  ADMIN_CREDIT: "Ricarica/Cashback",
  TRANSFER: "Trasferimento",
  PURCHASE_DEBIT: "Pagamento ordine (crediti)",
  REVERSAL: "Storno",
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

async function fetchMyWallet(): Promise<WalletRead> {
  const res = await fetch("/api/proxy/wallets/me");
  if (!res.ok) throw new Error("Impossibile caricare il wallet.");
  return res.json();
}

async function fetchMyTransactions(): Promise<WalletTransactionRead[]> {
  const res = await fetch("/api/proxy/wallets/me/transactions");
  if (!res.ok) throw new Error("Impossibile caricare le transazioni.");
  return res.json();
}

export function WalletPanel() {
  const queryClient = useQueryClient();
  const [toAddress, setToAddress] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);
  const [sendLoading, setSendLoading] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendSuccess, setSendSuccess] = useState(false);

  const { data: wallet, error: walletError } = useQuery({
    queryKey: ["wallet", "me"],
    queryFn: fetchMyWallet,
  });
  const { data: transactions, error: transactionsError } = useQuery({
    queryKey: ["wallet", "me", "transactions"],
    queryFn: fetchMyTransactions,
  });

  async function handleCopyAddress() {
    if (!wallet) return;
    try {
      await navigator.clipboard.writeText(wallet.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can fail (permissions, non-HTTPS context) -- the
      // address is still visible on screen to copy manually, so this is a
      // silent no-op, not an error worth surfacing.
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const amountCents = Math.round(parseFloat(amount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setSendError("Inserisci un importo valido.");
      return;
    }
    setSendLoading(true);
    setSendError(null);
    try {
      const res = await fetch("/api/proxy/wallets/transfer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_address: toAddress.trim(),
          amount_cents: amountCents,
          note: note || null,
          idempotency_key: crypto.randomUUID(),
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setSendSuccess(true);
      setToAddress("");
      setAmount("");
      setNote("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["wallet", "me"] }),
        queryClient.invalidateQueries({ queryKey: ["wallet", "me", "transactions"] }),
      ]);
      setTimeout(() => setSendSuccess(false), 3000);
    } catch (err: any) {
      setSendError(err.message || "Impossibile inviare il pagamento.");
    } finally {
      setSendLoading(false);
    }
  }

  if (walletError) {
    return <p className="text-sm text-rose-400">Impossibile caricare il wallet.</p>;
  }

  return (
    <div className="space-y-6">
      {/* Balance + address */}
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        {wallet === undefined ? (
          <p className="text-sm text-slate-500">Caricamento...</p>
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Saldo disponibile</p>
              <p className="text-3xl font-bold text-white light:text-slate-900">{euro(wallet.balance_cents)}</p>
            </div>
            <div>
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Il tuo indirizzo wallet</p>
              <button
                onClick={handleCopyAddress}
                title="Copia indirizzo"
                className="flex items-center gap-2 font-mono text-xs text-slate-300 light:text-slate-600 bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200 rounded-lg px-3 py-2 hover:bg-white/10 transition cursor-pointer"
              >
                {wallet.address}
                <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  {copied ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  )}
                </svg>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Send form -- only for wallets with can_transfer enabled (denied by
          default, turned on per promoter by an admin) */}
      {wallet && !wallet.can_transfer ? (
        <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <h3 className="text-sm font-semibold text-white light:text-slate-900 mb-2">Invia denaro</h3>
          <p className="text-xs text-slate-500">L'invio di bonifici wallet non è abilitato per il tuo account.</p>
        </div>
      ) : wallet ? (
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h3 className="text-sm font-semibold text-white light:text-slate-900 mb-4">Invia denaro</h3>
        <form onSubmit={handleSend} className="grid grid-cols-1 sm:grid-cols-[2fr_1fr_2fr_auto] gap-3 items-end">
          <div className="space-y-1">
            <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Indirizzo destinatario</label>
            <input
              required
              value={toAddress}
              onChange={(e) => setToAddress(e.target.value)}
              placeholder="0x..."
              className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Importo (EUR)</label>
            <input
              required
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0,00"
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Nota (opzionale)</label>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
          </div>
          <button
            type="submit"
            disabled={sendLoading}
            className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50 whitespace-nowrap"
          >
            {sendLoading ? "Invio..." : "Invia"}
          </button>
        </form>
        {sendError && (
          <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{sendError}</div>
        )}
        {sendSuccess && (
          <div className="mt-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">Pagamento inviato con successo.</div>
        )}
      </div>
      ) : null}

      {/* Transaction history */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="p-5 pb-3">
          <h3 className="text-sm font-semibold text-white light:text-slate-900">Storico transazioni</h3>
        </div>
        {transactionsError && <p className="px-5 pb-3 text-sm text-rose-400">Impossibile caricare le transazioni.</p>}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 px-5">Tipo</th>
                <th className="py-2 px-5">Controparte</th>
                <th className="py-2 px-5">Nota</th>
                <th className="py-2 px-5 text-right">Importo</th>
                <th className="py-2 px-5">Data</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {transactions === undefined ? (
                <tr><td colSpan={5} className="text-center py-6 text-slate-500">Caricamento...</td></tr>
              ) : transactions.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-6 text-slate-500">Nessuna transazione.</td></tr>
              ) : (
                transactions.map((t) => {
                  const isOutgoing = t.from_wallet_id === wallet?.id;
                  return (
                    <tr key={t.id} className="text-slate-300 light:text-slate-600">
                      <td className="py-2 px-5">{transactionLabel(t)}</td>
                      <td className="py-2 px-5">
                        {isOutgoing ? (t.to_display_name ?? "Sistema") : (t.from_display_name ?? "Sistema")}
                      </td>
                      <td className="py-2 px-5 text-slate-500">{t.note ?? "—"}</td>
                      <td className={`py-2 px-5 text-right font-semibold ${isOutgoing ? "text-rose-400" : "text-emerald-400"}`}>
                        {isOutgoing ? "-" : "+"}{euro(t.amount_cents)}
                      </td>
                      <td className="py-2 px-5">{new Date(t.created_at).toLocaleString("it-IT")}</td>
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
