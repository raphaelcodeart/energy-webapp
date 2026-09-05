"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { InvoiceRedemptionRead, PartnerRead } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "In verifica",
  PAYMENT_PENDING: "Da pagare",
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

async function fetchPartners(): Promise<PartnerRead[]> {
  const res = await fetch("/api/proxy/partners?active_only=true");
  if (!res.ok) throw new Error("Impossibile caricare i fornitori partner.");
  return res.json();
}

async function fetchMine(): Promise<InvoiceRedemptionRead[]> {
  const res = await fetch("/api/proxy/invoice-redemptions/mine");
  if (!res.ok) throw new Error("Impossibile caricare le tue richieste.");
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

/** "Riscatta Cashback" -- lets a customer or promoter turn proof of what
    they already paid an external energy partner (e.g. Eviso) into internal
    wallet credit. See docs/cashback-partner-invoices-plan.md for the full
    design: an admin verifies the document and the real amount, THEN the
    customer pays 3% by bank transfer, THEN an admin confirms that arrived
    -- only at that last step does any wallet credit get minted. */
export function InvoiceRedemptionPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [partnerId, setPartnerId] = useState("");
  const [amount, setAmount] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data: partners } = useQuery({ queryKey: ["invoice-redemptions", "partners"], queryFn: fetchPartners });
  const { data: mine, error: loadError } = useQuery({ queryKey: ["invoice-redemptions", "mine"], queryFn: fetchMine });
  const { data: paymentInfo } = useQuery({ queryKey: ["invoice-redemptions", "payment-info"], queryFn: fetchPaymentInfo });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !partnerId) return;
    const amountCents = Math.round(parseFloat(amount.replace(",", ".")) * 100);
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      setSubmitError("Inserisci un importo valido.");
      return;
    }
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const formData = new FormData();
      formData.append("partner_id", partnerId);
      formData.append("declared_amount_cents", String(amountCents));
      formData.append("file", file);
      const res = await fetch("/api/proxy/invoice-redemptions", { method: "POST", body: formData });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowForm(false);
      setPartnerId("");
      setAmount("");
      setFile(null);
      await queryClient.invalidateQueries({ queryKey: ["invoice-redemptions", "mine"] });
    } catch (err: any) {
      setSubmitError(err.message || "Impossibile inviare la richiesta.");
    } finally {
      setSubmitLoading(false);
    }
  }

  async function handleViewPhoto(id: string) {
    const res = await fetch(`/api/proxy/invoice-redemptions/mine/${id}/photo-url`);
    if (!res.ok) return;
    const { url } = await res.json();
    window.open(url, "_blank", "noopener,noreferrer");
  }

  function handleRowAction(r: InvoiceRedemptionRead) {
    if (r.status === "PAYMENT_PENDING") {
      setExpandedId(expandedId === r.id ? null : r.id);
    } else {
      handleViewPhoto(r.id);
    }
  }

  return (
    <div className="space-y-6">
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <div className="flex items-center justify-between gap-4 mb-1">
          <h3 className="text-sm font-semibold text-white light:text-slate-900">Riscatta Cashback</h3>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-3 py-1.5 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer"
          >
            {showForm ? "Annulla" : "Nuova richiesta"}
          </button>
        </div>
        <p className="text-xs text-slate-500">
          Hai già pagato una bolletta a uno dei nostri fornitori partner? Carica la foto e riscatta il suo valore in
          crediti, pagando solo il 3% del totale — riceverai il 100% + un ulteriore 3% di bonus.
        </p>

        {showForm && (
          <form onSubmit={handleSubmit} className="mt-4 pt-4 border-t border-white/5 light:border-slate-200 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Fornitore partner</label>
                <select
                  required
                  value={partnerId}
                  onChange={(e) => setPartnerId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  <option value="">Seleziona...</option>
                  {(partners ?? []).map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Importo totale della fattura (EUR)</label>
                <input
                  required
                  inputMode="decimal"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0,00"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
                />
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Foto o PDF della fattura</label>
              <input
                required
                type="file"
                accept="image/jpeg,image/png,application/pdf"
                capture="environment"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="w-full text-xs text-slate-300 light:text-slate-600 file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-white/10 file:text-slate-200 light:file:bg-slate-900/10 light:file:text-slate-700 file:text-xs file:font-semibold file:cursor-pointer cursor-pointer"
              />
            </div>
            <button
              type="submit"
              disabled={submitLoading}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
            >
              {submitLoading ? "Invio..." : "Invia per la verifica"}
            </button>
            {submitError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{submitError}</div>
            )}
          </form>
        )}
      </div>

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 divide-y divide-white/5 light:divide-slate-200 overflow-hidden">
        <div className="p-5 pb-3">
          <h3 className="text-sm font-semibold text-white light:text-slate-900">Le tue richieste</h3>
        </div>
        {loadError && <p className="px-5 pb-3 text-sm text-rose-400">Impossibile caricare le richieste.</p>}
        {mine === undefined ? (
          <p className="text-center py-8 text-slate-500 text-sm">Caricamento...</p>
        ) : mine.length === 0 ? (
          <p className="text-center py-8 text-slate-500 text-sm">Nessuna richiesta ancora.</p>
        ) : (
          mine.map((r) => (
            <div key={r.id} className="p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-white light:text-slate-900">{r.partner_name}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[r.status]}`}>
                      {STATUS_LABELS[r.status]}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">
                    Dichiarato: {euro(r.declared_amount_cents)}
                    {r.confirmed_amount_cents != null && <> · Confermato: {euro(r.confirmed_amount_cents)}</>}
                  </p>
                  {r.rejection_reason && <p className="text-[11px] text-rose-400 mt-1">{r.rejection_reason}</p>}
                </div>
                <button
                  onClick={() => handleRowAction(r)}
                  className="px-2.5 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer shrink-0"
                >
                  {r.status === "PAYMENT_PENDING" ? (expandedId === r.id ? "Nascondi" : "Come pagare") : "Vedi foto"}
                </button>
              </div>

              {r.status === "PAYMENT_PENDING" && expandedId === r.id && (
                <div className="mt-3 pt-3 border-t border-white/5 light:border-slate-200 text-xs space-y-1.5">
                  <p className="text-slate-300 light:text-slate-600">
                    Paga <strong className="text-orange-400">{euro(r.payment_due_cents ?? 0)}</strong> per riscattare{" "}
                    <strong className="text-emerald-400">{euro(r.confirmed_amount_cents ?? 0)}</strong> di credito.
                  </p>
                  {paymentInfo?.iban ? (
                    <>
                      <p><span className="text-slate-500">IBAN:</span> <span className="font-mono">{paymentInfo.iban}</span></p>
                      <p><span className="text-slate-500">Intestatario:</span> {paymentInfo.holder}</p>
                    </>
                  ) : (
                    <p className="text-slate-500">Contatta l'amministrazione per le coordinate bancarie.</p>
                  )}
                  <p><span className="text-slate-500">Causale (obbligatoria):</span> <span className="font-mono text-orange-400">{r.payment_reference_code}</span></p>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
