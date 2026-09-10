"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { ImportedOrderQuoteRead, ImportedOrderRead } from "@/lib/types";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function lialCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} LialCash`;
}

async function fetchQuote(importedProductId: string): Promise<ImportedOrderQuoteRead> {
  const res = await fetch(`/api/proxy/imported-products/orders/quote/mine?imported_product_id=${importedProductId}`);
  if (!res.ok) throw new Error("Impossibile calcolare il preventivo.");
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

function StepBadge({ n, done }: { n: number; done?: boolean }) {
  return (
    <span
      className={`flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold shrink-0 ${
        done ? "bg-emerald-500 text-white" : "bg-orange-600 text-white"
      }`}
    >
      {done ? (
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        n
      )}
    </span>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2.5 cursor-pointer group"
    >
      <span
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          checked ? "bg-orange-600" : "bg-white/15 light:bg-slate-300"
        }`}
      >
        <span
          className={`inline-block h-4.5 w-4.5 transform rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-6" : "translate-x-1"
          }`}
          style={{ height: "18px", width: "18px" }}
        />
      </span>
      <span className="text-sm font-semibold text-white light:text-slate-900">{label}</span>
    </button>
  );
}

/** Checkout for the Shop's "Acquisti LialEnergy" subcategory -- same
    LialCash-spend + OTP + payment-method mechanics as
    product-checkout-modal.tsx, minus the "riscuoti subito cashback" step:
    these products never generate cashback, only ever let a customer burn
    existing wallet balance (see imported_products/models.py). Talks to the
    imported-products domain's own parallel endpoints, never /orders/*. */
export function ImportedProductCheckoutModal({
  importedProductId,
  productName,
  onClose,
}: {
  importedProductId: string;
  productName: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: quote, error: quoteError } = useQuery({
    queryKey: ["customer", "imported-orders", "quote", importedProductId],
    queryFn: () => fetchQuote(importedProductId),
  });

  const [creditAmount, setCreditAmount] = useState("0.00");
  const [useCredit, setUseCredit] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<"BANK_TRANSFER" | "CARD" | null>(null);
  const [step, setStep] = useState<"choose" | "bank_instructions" | "card_redirect" | "success">("choose");
  const [placedOrder, setPlacedOrder] = useState<ImportedOrderRead | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [otpRequesting, setOtpRequesting] = useState(false);
  const [otpError, setOtpError] = useState<string | null>(null);

  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: step === "bank_instructions",
  });

  const maxUsableCents = quote ? Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents) : 0;

  useEffect(() => {
    if (!quote) return;
    setUseCredit(false);
    setCreditAmount("0.00");
    if (quote.bank_transfer_available) setPaymentMethod("BANK_TRANSFER");
    else if (quote.card_available) setPaymentMethod("CARD");
    else setPaymentMethod(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quote?.imported_product_id]);

  const creditCents = quote && useCredit
    ? Math.min(
        Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100),
        quote.max_creditable_cents,
        quote.customer_wallet_balance_cents
      )
    : 0;
  const effectiveDiscountPct = quote && quote.amount_cents > 0 ? Math.round((creditCents / quote.amount_cents) * 100) : 0;
  const residualCents = quote ? quote.amount_cents - creditCents : 0;
  const needsPaymentMethod = residualCents > 0;
  const noMethodAvailable = quote ? !quote.bank_transfer_available && !quote.card_available : false;
  const otpConfirmed = creditCents === 0 || !!otpCode.trim();

  function setCreditFraction(fraction: number) {
    const cents = Math.round(maxUsableCents * fraction);
    setCreditAmount((cents / 100).toFixed(2));
    setOtpRequested(false);
    setOtpCode("");
  }

  function handleToggleCredit(next: boolean) {
    setUseCredit(next);
    setOtpRequested(false);
    setOtpCode("");
    setCreditAmount(next ? (maxUsableCents / 100).toFixed(2) : "0.00");
  }

  async function handleRequestOtp() {
    setOtpRequesting(true);
    setOtpError(null);
    try {
      const res = await fetch("/api/proxy/imported-products/orders/mine/request-credit-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imported_product_id: importedProductId, credit_applied_cents: creditCents }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setOtpRequested(true);
    } catch (err: any) {
      setOtpError(err.message || "Impossibile inviare il codice.");
    } finally {
      setOtpRequesting(false);
    }
  }

  async function handleConfirm() {
    if (!quote) return;
    if (needsPaymentMethod && !paymentMethod) {
      setSubmitError("Seleziona un metodo di pagamento.");
      return;
    }
    if (creditCents > 0 && !otpCode.trim()) {
      setSubmitError("Inserisci il codice di conferma ricevuto via email per usare i tuoi LialCash.");
      return;
    }
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const res = await fetch("/api/proxy/imported-products/orders/mine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          imported_product_id: importedProductId,
          credit_applied_cents: creditCents,
          otp_code: creditCents > 0 ? otpCode.trim() : null,
          payment_method: needsPaymentMethod ? paymentMethod : "BANK_TRANSFER",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const order: ImportedOrderRead = await res.json();
      setPlacedOrder(order);
      await queryClient.invalidateQueries({ queryKey: ["customer", "wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });

      if (order.status === "PAID") {
        setStep("success");
        return;
      }
      if (order.payment_method === "CARD") {
        const returnUrl = window.location.href;
        const sessionRes = await fetch(
          `/api/proxy/imported-products/orders/mine/${order.id}/checkout-session?success_url=${encodeURIComponent(returnUrl)}&cancel_url=${encodeURIComponent(returnUrl)}`,
          { method: "POST" }
        );
        if (!sessionRes.ok) throw new Error(await friendlyApiError(sessionRes));
        const { checkout_url } = await sessionRes.json();
        window.open(checkout_url, "_blank", "noopener,noreferrer");
        setStep("card_redirect");
        return;
      }
      setStep("bank_instructions");
    } catch (err: any) {
      setSubmitError(err.message || "Impossibile completare l'acquisto.");
    } finally {
      setSubmitLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-xl glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white light:text-slate-900">Acquista {quote ? "" : productName}</h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/10 light:hover:bg-slate-900/10 text-slate-400 transition cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {quoteError && <p className="text-sm text-rose-400">Impossibile caricare il preventivo.</p>}
        {step === "choose" && !quote && !quoteError && (
          <div className="py-10 text-center text-sm text-slate-500">Caricamento preventivo...</div>
        )}

        {step === "success" && placedOrder && (
          <div className="text-center py-6 space-y-3">
            <svg className="w-14 h-14 text-emerald-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm text-slate-300 light:text-slate-600">
              Ordine confermato -- pagato interamente con i tuoi LialCash.
            </p>
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer"
            >
              Chiudi
            </button>
          </div>
        )}

        {step === "card_redirect" && placedOrder && (
          <div className="text-center py-6 space-y-3">
            <svg className="w-14 h-14 text-orange-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            <p className="text-sm text-slate-300 light:text-slate-600">
              Abbiamo aperto Stripe in una nuova scheda per completare il pagamento di{" "}
              <strong className="text-orange-400">{euro(placedOrder.residual_amount_cents)}</strong>.
            </p>
            <p className="text-xs text-slate-500">
              Puoi tornare qui in qualsiasi momento: trovi l&apos;ordine anche in &ldquo;I miei Ordini&rdquo;.
            </p>
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer"
            >
              Chiudi
            </button>
          </div>
        )}

        {step === "bank_instructions" && placedOrder && (
          <div className="space-y-3">
            <p className="text-sm text-slate-300 light:text-slate-600">
              Ordine creato. Paga <strong className="text-orange-400">{euro(placedOrder.residual_amount_cents)}</strong> tramite
              bonifico per confermarlo.
            </p>
            <div className="p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200 text-xs space-y-1.5">
              {paymentInfo?.iban ? (
                <>
                  <p><span className="text-slate-500">IBAN:</span> <span className="font-mono">{paymentInfo.iban}</span></p>
                  <p><span className="text-slate-500">Intestatario:</span> {paymentInfo.holder}</p>
                  {paymentInfo.instructions && <p className="text-slate-400 light:text-slate-500 pt-1">{paymentInfo.instructions}</p>}
                </>
              ) : (
                <p className="text-slate-500">Contatta l&apos;amministrazione per le coordinate bancarie.</p>
              )}
              <p className="pt-1"><span className="text-slate-500">Causale consigliata:</span> <span className="font-mono text-orange-400">Ordine {placedOrder.id.slice(0, 8).toUpperCase()}</span></p>
            </div>
            <button
              onClick={onClose}
              className="w-full px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer"
            >
              Ho capito
            </button>
          </div>
        )}

        {step === "choose" && quote && (
          <div className="space-y-5">
            <div className="p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
              <p className="text-sm font-semibold text-white light:text-slate-900 mb-2">{quote.product_name}</p>
              <div className="flex items-end gap-3 flex-wrap">
                <div>
                  <p className="text-[10px] text-slate-500 uppercase tracking-wide">
                    {creditCents > 0 ? "Prezzo scontato" : "Prezzo"}
                  </p>
                  <p className={`text-2xl font-extrabold ${creditCents > 0 ? "text-emerald-400" : "text-white light:text-slate-900"}`}>
                    {euro(Math.max(residualCents, 0))}
                  </p>
                </div>
                {creditCents > 0 && (
                  <div className="pb-1">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wide">Prezzo pieno</p>
                    <p className="text-sm text-slate-500 line-through">{euro(quote.amount_cents)}</p>
                  </div>
                )}
                {creditCents > 0 && (
                  <span className="mb-1 px-2 py-1 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    -{effectiveDiscountPct}%
                  </span>
                )}
              </div>
              {quote.max_creditable_cents > 0 && (
                <p className="text-[11px] text-slate-500 mt-2">
                  Il tuo saldo: <strong className="text-white light:text-slate-900">{lialCash(quote.customer_wallet_balance_cents)}</strong>
                  {" "}· su questo prodotto puoi usarne fino a {lialCash(maxUsableCents)} (max {quote.credit_discount_percentage}% di sconto)
                </p>
              )}
            </div>

            {quote.max_creditable_cents > 0 && (
              <div className="p-4 rounded-xl border border-white/10 light:border-slate-200 space-y-3">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2.5">
                    <StepBadge n={1} />
                    <Toggle checked={useCredit} onChange={handleToggleCredit} label="Usa i tuoi LialCash per abbassare il prezzo" />
                  </div>
                </div>

                {useCredit && (
                  <div className="pl-8 space-y-3">
                    <p className="text-[11px] text-slate-500">
                      I tuoi LialCash valgono 1:1 come sconto: ogni LialCash speso abbassa il prezzo di 1&euro;.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {[0.25, 0.5, 0.75, 1].map((fraction) => {
                        const presetCents = Math.round(maxUsableCents * fraction);
                        const isActive = Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100) === presetCents;
                        return (
                          <button
                            key={fraction}
                            type="button"
                            onClick={() => setCreditFraction(fraction)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                              isActive
                                ? "bg-orange-600 border-orange-600 text-white"
                                : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                            }`}
                          >
                            {fraction === 1 ? "Massimo" : `${Math.round(fraction * 100)}%`}
                          </button>
                        );
                      })}
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase shrink-0">
                        Importo personalizzato
                      </label>
                      <input
                        inputMode="decimal"
                        value={creditAmount}
                        onChange={(e) => { setCreditAmount(e.target.value); setOtpRequested(false); setOtpCode(""); }}
                        className="w-full max-w-[140px] rounded-lg glass-input px-3 py-1.5 text-sm focus:border-orange-500"
                      />
                      <span className="text-xs text-slate-500 shrink-0">LialCash</span>
                    </div>
                    <p className="text-xs px-3 py-2 rounded-lg bg-orange-500/10 border border-orange-500/20 text-orange-300">
                      Stai usando <strong>{lialCash(creditCents)}</strong> = <strong>{effectiveDiscountPct}% di sconto</strong> su questo ordine.
                    </p>
                  </div>
                )}
              </div>
            )}

            {creditCents > 0 && (
              <div className="p-4 rounded-xl border border-white/10 light:border-slate-200 space-y-2.5">
                <div className="flex items-center gap-2.5">
                  <StepBadge n={2} done={!!otpCode.trim()} />
                  <p className="text-sm font-semibold text-white light:text-slate-900">Conferma via email</p>
                </div>
                <p className="text-[11px] text-slate-500 pl-8">
                  Per sicurezza, ti mandiamo un codice via email per confermare l&apos;uso dei tuoi LialCash su questo ordine.
                </p>
                <div className="pl-8">
                  {!otpRequested ? (
                    <button
                      type="button"
                      onClick={handleRequestOtp}
                      disabled={otpRequesting}
                      className="px-4 py-2 rounded-lg bg-orange-600/15 hover:bg-orange-600/25 border border-orange-500/30 text-xs font-semibold text-orange-400 transition cursor-pointer disabled:opacity-50"
                    >
                      {otpRequesting ? "Invio in corso..." : "Invia codice via email"}
                    </button>
                  ) : (
                    <div className="space-y-1.5">
                      <p className="text-[11px] text-emerald-400 flex items-center gap-1">
                        <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                        </svg>
                        Codice inviato -- controlla la tua email
                      </p>
                      <div className="flex items-center gap-2">
                        <input
                          inputMode="numeric"
                          autoFocus
                          value={otpCode}
                          onChange={(e) => setOtpCode(e.target.value)}
                          placeholder="Codice ricevuto via email"
                          className="w-full max-w-[200px] rounded-lg glass-input px-3 py-2 text-sm font-mono tracking-wider focus:border-orange-500"
                        />
                        <button
                          type="button"
                          onClick={handleRequestOtp}
                          disabled={otpRequesting}
                          className="text-[11px] font-semibold text-orange-400 hover:text-orange-300 cursor-pointer disabled:opacity-50"
                        >
                          Rinvia
                        </button>
                      </div>
                    </div>
                  )}
                  {otpError && <p className="text-[11px] text-rose-400 mt-1.5">{otpError}</p>}
                </div>
              </div>
            )}

            {needsPaymentMethod && (
              <div className="p-4 rounded-xl border border-white/10 light:border-slate-200 space-y-2.5">
                <div className="flex items-center gap-2.5">
                  <StepBadge n={creditCents > 0 ? 3 : 2} done={!!paymentMethod} />
                  <p className="text-sm font-semibold text-white light:text-slate-900">Come vuoi pagare il resto?</p>
                </div>
                {noMethodAvailable ? (
                  <p className="text-xs text-rose-400 pl-8">
                    Nessun metodo di pagamento è al momento disponibile per completare questo ordine. Contatta l&apos;amministrazione.
                  </p>
                ) : (
                  <div className="pl-8 flex gap-2.5">
                    {quote.bank_transfer_available && (
                      <button
                        type="button"
                        onClick={() => setPaymentMethod("BANK_TRANSFER")}
                        className={`flex-1 flex items-center justify-center gap-2 px-3 py-3 rounded-xl text-sm font-semibold border-2 transition cursor-pointer ${
                          paymentMethod === "BANK_TRANSFER"
                            ? "bg-orange-600 border-orange-600 text-white shadow-lg shadow-orange-500/20"
                            : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                        }`}
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 21h18M4 10h16M4 10l8-6 8 6M6 10v9m4-9v9m4-9v9m4-9v9" />
                        </svg>
                        Bonifico
                      </button>
                    )}
                    {quote.card_available && (
                      <button
                        type="button"
                        onClick={() => setPaymentMethod("CARD")}
                        className={`flex-1 flex items-center justify-center gap-2 px-3 py-3 rounded-xl text-sm font-semibold border-2 transition cursor-pointer ${
                          paymentMethod === "CARD"
                            ? "bg-orange-600 border-orange-600 text-white shadow-lg shadow-orange-500/20"
                            : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                        }`}
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M2 10h20M6 15h4M2 7a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V7z" />
                        </svg>
                        Carta
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="p-4 rounded-xl bg-gradient-to-br from-orange-600/10 to-amber-500/5 border border-orange-500/20 space-y-1.5">
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-400 light:text-slate-500">Prezzo prodotto</p>
                <p className="text-xs text-slate-400 light:text-slate-500">{euro(quote.amount_cents)}</p>
              </div>
              {creditCents > 0 && (
                <div className="flex items-center justify-between">
                  <p className="text-xs text-slate-400 light:text-slate-500">LialCash usati</p>
                  <p className="text-xs text-emerald-400">-{lialCash(creditCents)}</p>
                </div>
              )}
              <div className="flex items-center justify-between pt-1.5 border-t border-white/10 light:border-slate-300">
                <p className="text-sm font-bold text-white light:text-slate-900">Totale da pagare ora</p>
                <p className={`text-xl font-extrabold ${residualCents > 0 ? "text-orange-400" : "text-emerald-400"}`}>
                  {euro(Math.max(residualCents, 0))}
                </p>
              </div>
              {residualCents <= 0 && (
                <p className="text-[11px] text-emerald-400 text-right">Coperto interamente dai tuoi LialCash</p>
              )}
            </div>

            {submitError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{submitError}</div>
            )}

            <button
              onClick={handleConfirm}
              disabled={
                submitLoading
                || (needsPaymentMethod && (noMethodAvailable || !paymentMethod))
                || !otpConfirmed
              }
              className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.99]"
            >
              {submitLoading ? "Elaborazione..." : residualCents > 0 ? "Conferma e procedi al pagamento" : "Conferma ordine"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
