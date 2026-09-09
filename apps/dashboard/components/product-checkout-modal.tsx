"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { OrderQuoteRead, OrderRead } from "@/lib/types";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

async function fetchQuote(productVersionId: string): Promise<OrderQuoteRead> {
  const res = await fetch(`/api/proxy/orders/quote/mine?product_version_id=${productVersionId}`);
  if (!res.ok) throw new Error("Impossibile calcolare il preventivo.");
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

/** Self-checkout for a DROPSHIPPING/PARTNER product (never INTERNAL, which
    has no "Acquista" button at all -- see customer-products-panel.tsx).
    Three steps: pick how much wallet credit to apply (capped by the
    product's own percentage and the customer's balance), pick how to pay
    the residual (bonifico/carta -- each hidden entirely when not
    configured, never just disabled-but-visible), then either see bank
    transfer instructions or get redirected to Stripe Checkout. See
    docs/cashback-partner-invoices-plan.md. */
export function ProductCheckoutModal({
  productVersionId,
  productName,
  onClose,
}: {
  productVersionId: string;
  productName: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: quote, error: quoteError } = useQuery({
    queryKey: ["customer", "orders", "quote", productVersionId],
    queryFn: () => fetchQuote(productVersionId),
  });

  const [creditAmount, setCreditAmount] = useState("0.00");
  const [paymentMethod, setPaymentMethod] = useState<"BANK_TRANSFER" | "CARD" | null>(null);
  const [cashbackRequested, setCashbackRequested] = useState(false);
  const [step, setStep] = useState<"choose" | "bank_instructions" | "card_redirect" | "success">("choose");
  const [placedOrder, setPlacedOrder] = useState<OrderRead | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Spending existing LialCash needs a fresh OTP emailed to the customer
  // first -- see orders/service.py::create_order's otp_code parameter and
  // POST /orders/mine/request-credit-otp. Irrelevant (and never shown) when
  // no wallet credit is being applied to this order.
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [otpRequesting, setOtpRequesting] = useState(false);
  const [otpError, setOtpError] = useState<string | null>(null);

  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: step === "bank_instructions",
  });

  useEffect(() => {
    if (!quote) return;
    const maxUsable = Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents);
    setCreditAmount((maxUsable / 100).toFixed(2));
    // Default to whichever residual payment method is actually available.
    if (quote.bank_transfer_available) setPaymentMethod("BANK_TRANSFER");
    else if (quote.card_available) setPaymentMethod("CARD");
    else setPaymentMethod(null);
  }, [quote]);

  const creditCents = quote
    ? Math.min(
        Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100),
        quote.max_creditable_cents,
        quote.customer_wallet_balance_cents
      )
    : 0;
  const residualCents = quote ? quote.amount_cents - creditCents : 0;
  const canRequestCashback = !!quote?.cashback_available && residualCents > 0;
  const cashbackSurchargeCents = canRequestCashback && cashbackRequested
    ? Math.round((residualCents * (quote?.cashback_percentage ?? 0)) / 100)
    : 0;
  const totalToPayCents = residualCents + cashbackSurchargeCents;
  const needsPaymentMethod = totalToPayCents > 0;
  const noMethodAvailable = quote ? !quote.bank_transfer_available && !quote.card_available : false;

  async function handleRequestOtp() {
    setOtpRequesting(true);
    setOtpError(null);
    try {
      const res = await fetch("/api/proxy/orders/mine/request-credit-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_version_id: productVersionId, credit_applied_cents: creditCents }),
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
      const res = await fetch("/api/proxy/orders/mine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_version_id: productVersionId,
          credit_applied_cents: creditCents,
          cashback_requested: cashbackRequested,
          otp_code: creditCents > 0 ? otpCode.trim() : null,
          payment_method: needsPaymentMethod ? paymentMethod : "BANK_TRANSFER",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const order: OrderRead = await res.json();
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
          `/api/proxy/orders/mine/${order.id}/checkout-session?success_url=${encodeURIComponent(returnUrl)}&cancel_url=${encodeURIComponent(returnUrl)}`,
          { method: "POST" }
        );
        if (!sessionRes.ok) throw new Error(await friendlyApiError(sessionRes));
        const { checkout_url } = await sessionRes.json();
        // Opens in a NEW TAB rather than navigating away -- if the payment
        // fails or Stripe hiccups, the customer never loses this page (and
        // whatever else they had open in the dashboard).
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
      <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
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
                <p className="text-slate-500">Contatta l'amministrazione per le coordinate bancarie.</p>
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
          <div className="space-y-4">
            <p className="text-sm text-slate-300 light:text-slate-600">{quote.product_name}</p>
            <div className="grid grid-cols-3 gap-3 text-xs p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Prezzo</p>
                <p className="font-semibold text-white light:text-slate-900">{euro(quote.amount_cents)}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Sconto max LialCash</p>
                <p className="font-semibold text-orange-400">{quote.credit_discount_percentage}%</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Il tuo saldo</p>
                <p className="font-semibold text-white light:text-slate-900">{euro(quote.customer_wallet_balance_cents)} LialCash</p>
              </div>
            </div>

            {quote.max_creditable_cents > 0 && (
              <div className="space-y-1">
                <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
                  LialCash da usare (max {euro(Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents))})
                </label>
                <input
                  inputMode="decimal"
                  value={creditAmount}
                  onChange={(e) => { setCreditAmount(e.target.value); setOtpRequested(false); setOtpCode(""); }}
                  className="w-full max-w-[160px] rounded-lg glass-input px-3 py-1.5 text-sm focus:border-orange-500"
                />
              </div>
            )}

            {creditCents > 0 && (
              <div className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200 space-y-2">
                <p className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase">
                  Conferma utilizzo LialCash
                </p>
                <p className="text-[11px] text-slate-500">
                  Per sicurezza, ti mandiamo un codice via email per confermare l&apos;uso dei tuoi LialCash su questo ordine.
                </p>
                {!otpRequested ? (
                  <button
                    type="button"
                    onClick={handleRequestOtp}
                    disabled={otpRequesting}
                    className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                  >
                    {otpRequesting ? "Invio in corso..." : "Invia codice via email"}
                  </button>
                ) : (
                  <div className="flex items-center gap-2">
                    <input
                      inputMode="numeric"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value)}
                      placeholder="Codice ricevuto via email"
                      className="w-full max-w-[180px] rounded-lg glass-input px-3 py-1.5 text-sm focus:border-orange-500"
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
                )}
                {otpError && <p className="text-[11px] text-rose-400">{otpError}</p>}
              </div>
            )}

            {canRequestCashback && (
              <label className="flex items-start gap-2.5 text-xs text-slate-300 light:text-slate-600 cursor-pointer p-3 rounded-xl bg-orange-500/5 border border-orange-500/20">
                <input
                  type="checkbox"
                  checked={cashbackRequested}
                  onChange={(e) => setCashbackRequested(e.target.checked)}
                  className="mt-0.5 w-4 h-4 rounded border-white/20 accent-orange-500 shrink-0"
                />
                <span>
                  <strong className="text-orange-400">Riscuoti subito cashback:</strong> paga il {quote.cashback_percentage}% in
                  più ({euro(Math.round((residualCents * quote.cashback_percentage) / 100))}) e ricevi l&apos;intero importo
                  pagato accreditato come LialCash sul tuo wallet non appena il pagamento è confermato.
                </span>
              </label>
            )}

            <div className="pt-3 border-t border-white/5 light:border-slate-200">
              <p className="text-sm text-slate-300 light:text-slate-600 mb-2">
                Residuo da pagare: <strong className={totalToPayCents > 0 ? "text-orange-400" : "text-emerald-400"}>{euro(Math.max(totalToPayCents, 0))}</strong>
                {totalToPayCents <= 0 && " -- coperto interamente dai LialCash"}
                {cashbackSurchargeCents > 0 && (
                  <span className="text-[11px] text-slate-500"> (include {euro(cashbackSurchargeCents)} di cashback)</span>
                )}
              </p>

              {needsPaymentMethod && (
                <>
                  {noMethodAvailable ? (
                    <p className="text-xs text-rose-400">
                      Nessun metodo di pagamento è al momento disponibile per completare questo ordine. Contatta l'amministrazione.
                    </p>
                  ) : (
                    <div className="flex gap-2">
                      {quote.bank_transfer_available && (
                        <button
                          type="button"
                          onClick={() => setPaymentMethod("BANK_TRANSFER")}
                          className={`flex-1 px-3 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                            paymentMethod === "BANK_TRANSFER"
                              ? "bg-orange-600 border-orange-600 text-white"
                              : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                          }`}
                        >
                          Bonifico
                        </button>
                      )}
                      {quote.card_available && (
                        <button
                          type="button"
                          onClick={() => setPaymentMethod("CARD")}
                          className={`flex-1 px-3 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                            paymentMethod === "CARD"
                              ? "bg-orange-600 border-orange-600 text-white"
                              : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                          }`}
                        >
                          Carta
                        </button>
                      )}
                    </div>
                  )}
                </>
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
                || (creditCents > 0 && !otpCode.trim())
              }
              className="w-full px-4 py-2.5 rounded-xl bg-orange-600 hover:bg-orange-500 text-sm font-semibold text-white transition cursor-pointer disabled:opacity-50"
            >
              {submitLoading ? "Elaborazione..." : totalToPayCents > 0 ? "Conferma e procedi al pagamento" : "Conferma ordine"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
