"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { InvoiceRedemptionRead } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "Da verificare",
  PAYMENT_PENDING: "Attesa pagamento 3%",
  CREDITED: "Accreditata",
  REJECTED: "Rifiutata",
};
const STATUS_COLORS: Record<string, string> = {
  SUBMITTED: "bg-sky-500/10 text-sky-400 border-sky-500/20",
  PAYMENT_PENDING: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  CREDITED: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  REJECTED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

async function fetchQueue(statusFilter: string): Promise<InvoiceRedemptionRead[]> {
  const qs = statusFilter !== "ALL" ? `?status_filter=${statusFilter}` : "";
  const res = await fetch(`/api/proxy/invoice-redemptions/admin${qs}`);
  if (!res.ok) throw new Error("Impossibile caricare le richieste di riscatto.");
  return res.json();
}

/** Admin queue for the partner-invoice cashback flow -- see
    docs/cashback-partner-invoices-plan.md. Two real admin actions per
    redemption: "verify" (confirms the real amount, opens the 3% payment
    window) and "confirm-payment" (mints the wallet credit) -- both are
    money-adjacent so this whole panel is wallet.manage-gated server-side. */
export function AdminInvoiceRedemptionsPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("SUBMITTED");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [verifyAmount, setVerifyAmount] = useState("");
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const { data: queue, error: loadError } = useQuery({
    queryKey: ["admin", "invoice-redemptions", statusFilter],
    queryFn: () => fetchQueue(statusFilter),
  });

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "invoice-redemptions"] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
  }

  async function handleViewPhoto(id: string) {
    const res = await fetch(`/api/proxy/invoice-redemptions/admin/${id}/photo-url`);
    if (!res.ok) return;
    const { url } = await res.json();
    window.open(url, "_blank", "noopener,noreferrer");
  }

  async function handleVerify(id: string) {
    const amountCents = Math.round(parseFloat(verifyAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setActionError("Inserisci un importo valido.");
      return;
    }
    setActionLoadingId(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/invoice-redemptions/admin/${id}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed_amount_cents: amountCents }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setExpandedId(null);
      setVerifyAmount("");
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || "Impossibile verificare la richiesta.");
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleConfirmPayment(id: string) {
    setActionLoadingId(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/invoice-redemptions/admin/${id}/confirm-payment`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || "Impossibile confermare il pagamento.");
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleReject(id: string) {
    if (!rejectReason.trim()) return;
    setActionLoadingId(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/invoice-redemptions/admin/${id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason.trim() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setRejectingId(null);
      setRejectReason("");
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || "Impossibile rifiutare la richiesta.");
    } finally {
      setActionLoadingId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {["SUBMITTED", "PAYMENT_PENDING", "CREDITED", "REJECTED", "ALL"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
              statusFilter === s
                ? "bg-orange-600 border-orange-600 text-white"
                : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
            }`}
          >
            {s === "ALL" ? "Tutte" : STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {actionError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{actionError}</div>
      )}
      {loadError && <p className="text-sm text-rose-400">Impossibile caricare le richieste.</p>}

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 divide-y divide-white/5 light:divide-slate-200 overflow-hidden">
        {queue === undefined ? (
          <p className="text-center py-8 text-slate-500 text-sm">Caricamento...</p>
        ) : queue.length === 0 ? (
          <p className="text-center py-8 text-slate-500 text-sm">Nessuna richiesta in questo stato.</p>
        ) : (
          queue.map((r) => (
            <div key={r.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-white light:text-slate-900">{r.customer_display_name}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[r.status]}`}>
                      {STATUS_LABELS[r.status]}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">
                    Partner: {r.partner_name} · Dichiarato: {euro(r.declared_amount_cents)}
                    {r.confirmed_amount_cents != null && <> · Confermato: {euro(r.confirmed_amount_cents)}</>}
                  </p>
                  {r.payment_reference_code && (
                    <p className="text-[11px] font-mono text-slate-500 mt-1">
                      Codice bonifico: {r.payment_reference_code}
                      {r.payment_due_cents != null && <> · Atteso: {euro(r.payment_due_cents)}</>}
                    </p>
                  )}
                  {r.rejection_reason && (
                    <p className="text-[11px] text-rose-400 mt-1">Motivo rifiuto: {r.rejection_reason}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-wrap justify-end">
                  <button
                    onClick={() => handleViewPhoto(r.id)}
                    className="px-2.5 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
                  >
                    Vedi documento
                  </button>
                  {r.status === "SUBMITTED" && (
                    <button
                      onClick={() => { setExpandedId(expandedId === r.id ? null : r.id); setVerifyAmount((r.declared_amount_cents / 100).toFixed(2)); }}
                      className="px-2.5 py-1.5 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer"
                    >
                      Verifica importo
                    </button>
                  )}
                  {r.status === "PAYMENT_PENDING" && (
                    <button
                      onClick={() => handleConfirmPayment(r.id)}
                      disabled={actionLoadingId === r.id}
                      className="px-2.5 py-1.5 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                    >
                      {actionLoadingId === r.id ? "..." : "Conferma bonifico ricevuto"}
                    </button>
                  )}
                  {(r.status === "SUBMITTED" || r.status === "PAYMENT_PENDING") && (
                    <button
                      onClick={() => setRejectingId(rejectingId === r.id ? null : r.id)}
                      className="px-2.5 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer"
                    >
                      Rifiuta
                    </button>
                  )}
                </div>
              </div>

              {expandedId === r.id && (
                <div className="mt-3 pt-3 border-t border-white/5 light:border-slate-200 flex items-end gap-2">
                  <div className="space-y-1">
                    <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Importo reale della fattura (EUR)</label>
                    <input
                      autoFocus
                      inputMode="decimal"
                      value={verifyAmount}
                      onChange={(e) => setVerifyAmount(e.target.value)}
                      className="rounded-lg glass-input px-3 py-1.5 text-sm w-40 focus:border-orange-500"
                    />
                  </div>
                  <button
                    onClick={() => handleVerify(r.id)}
                    disabled={actionLoadingId === r.id}
                    className="px-4 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                  >
                    {actionLoadingId === r.id ? "..." : "Conferma importo"}
                  </button>
                  <p className="text-[11px] text-slate-500 pb-2">
                    Il cliente verrà avvisato di pagare il 3% ({(() => {
                      const v = Math.round(parseFloat(verifyAmount.replace(",", ".")) * 100);
                      return Number.isFinite(v) ? euro(Math.round(v * 0.03)) : "—";
                    })()})
                  </p>
                </div>
              )}

              {rejectingId === r.id && (
                <div className="mt-3 pt-3 border-t border-white/5 light:border-slate-200 flex items-end gap-2">
                  <div className="space-y-1 flex-1 max-w-sm">
                    <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Motivo del rifiuto</label>
                    <input
                      autoFocus
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      className="w-full rounded-lg glass-input px-3 py-1.5 text-sm focus:border-orange-500"
                    />
                  </div>
                  <button
                    onClick={() => handleReject(r.id)}
                    disabled={actionLoadingId === r.id}
                    className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                  >
                    {actionLoadingId === r.id ? "..." : "Conferma rifiuto"}
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
