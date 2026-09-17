"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { ProductThumbnail } from "@/components/product-thumbnail";
import type { CjOrderRead, CjProductRead, CjQuoteRead, CustomerRead } from "@/lib/types";

const MAX_QUANTITY = 10;

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function lialCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} LialCash`;
}

async function fetchQuote(variantId: string, quantity: number): Promise<CjQuoteRead> {
  const res = await fetch(`/api/proxy/cj/orders/quote/mine?variant_id=${variantId}&quantity=${quantity}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function fetchMyCustomer(): Promise<CustomerRead | null> {
  const res = await fetch("/api/proxy/customers/me");
  if (!res.ok) return null;
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

type Address = {
  recipient_name: string;
  recipient_phone: string;
  address_line1: string;
  address_line2: string;
  city: string;
  province: string;
  postal_code: string;
};

const inputClass =
  "w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500";

function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="block text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1">{label}</span>
      {children}
    </label>
  );
}

function Section({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <div className="p-4 rounded-xl border border-white/10 light:border-slate-200 space-y-3">
      <div className="flex items-center gap-2.5">
        <span className={`flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold shrink-0 text-white ${done ? "bg-emerald-500" : "bg-orange-600"}`}>
          {done ? "✓" : n}
        </span>
        <p className="text-sm font-semibold text-white light:text-slate-900">{title}</p>
      </div>
      {children}
    </div>
  );
}

/** Shop Lial Partner: product page and checkout in one window.
 *
 *  First the product -- photos, variants, quantity, delivery time -- then the
 *  checkout the customer already knows from the other shops (LialCash with
 *  an email code, bonifico or carta for the rest), plus the delivery
 *  address. Every amount is recomputed by the server: shipping is quoted by
 *  the supplier live for this variant and quantity.
 */
export function CjProductModal({ product, onClose }: { product: CjProductRead; onClose: () => void }) {
  const queryClient = useQueryClient();
  const firstAvailable = product.variants.find((v) => v.in_stock) ?? product.variants[0];
  const [variantId, setVariantId] = useState<string>(firstAvailable?.id ?? "");
  const [quantity, setQuantity] = useState(1);
  const [imageIndex, setImageIndex] = useState(0);
  const [imageOverride, setImageOverride] = useState<string | null>(null);
  const [showFullDescription, setShowFullDescription] = useState(false);
  const [step, setStep] = useState<"product" | "checkout" | "bank_instructions" | "card_redirect" | "success">("product");

  const variant = product.variants.find((v) => v.id === variantId) ?? null;
  const gallery = product.images.length > 0 ? product.images : product.image_url ? [product.image_url] : [];
  const mainImage = imageOverride ?? gallery[imageIndex] ?? null;

  const { data: quote, error: quoteError, isFetching: quoteLoading } = useQuery({
    queryKey: ["customer", "cj", "quote", variantId, quantity],
    queryFn: () => fetchQuote(variantId, quantity),
    enabled: step === "checkout" && !!variantId,
    retry: false,
  });
  const { data: me } = useQuery({ queryKey: ["customer", "me", "record"], queryFn: fetchMyCustomer, enabled: step === "checkout" });

  // Prefilled from the customer's record; what they type wins.
  const [addressEdits, setAddressEdits] = useState<Partial<Address>>({});
  const address: Address = {
    recipient_name: [me?.first_name, me?.last_name].filter(Boolean).join(" "),
    recipient_phone: me?.phone ?? "",
    address_line1: quote?.default_address.street ?? "",
    address_line2: "",
    city: quote?.default_address.city ?? "",
    province: quote?.default_address.province ?? "",
    postal_code: quote?.default_address.postal_code ?? "",
    ...addressEdits,
  };
  const setAddress = (next: Address) => setAddressEdits(next);

  const [useCredit, setUseCredit] = useState(false);
  const [creditAmount, setCreditAmount] = useState("0.00");
  const [chosenMethod, setPaymentMethod] = useState<"BANK_TRANSFER" | "CARD" | null>(null);
  const paymentMethod = chosenMethod
    ?? (quote?.bank_transfer_available ? "BANK_TRANSFER" : quote?.card_available ? "CARD" : null);
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [otpRequesting, setOtpRequesting] = useState(false);
  const [otpError, setOtpError] = useState<string | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [placedOrder, setPlacedOrder] = useState<CjOrderRead | null>(null);

  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: step === "bank_instructions",
  });

  const maxUsableCents = quote ? Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents) : 0;
  const creditCents = quote && useCredit
    ? Math.max(0, Math.min(Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100), maxUsableCents))
    : 0;
  const residualCents = quote ? quote.amount_cents - creditCents : 0;
  const needsPaymentMethod = residualCents > 0;
  const noMethodAvailable = quote ? !quote.bank_transfer_available && !quote.card_available : false;
  const addressComplete =
    address.recipient_name.trim().length >= 2 && address.recipient_phone.trim().length >= 6 &&
    address.address_line1.trim().length >= 3 && !!address.city.trim() && !!address.province.trim() &&
    address.postal_code.trim().length >= 3;

  function resetOtp() {
    setOtpRequested(false);
    setOtpCode("");
  }

  function changeQuantity(next: number) {
    setQuantity(Math.max(1, Math.min(MAX_QUANTITY, next)));
    setUseCredit(false);
    setCreditAmount("0.00");
    resetOtp();
  }

  async function handleRequestOtp() {
    setOtpRequesting(true);
    setOtpError(null);
    try {
      const res = await fetch("/api/proxy/cj/orders/mine/request-credit-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ variant_id: variantId, quantity, credit_applied_cents: creditCents }),
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
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const res = await fetch("/api/proxy/cj/orders/mine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          variant_id: variantId,
          quantity,
          address: {
            recipient_name: address.recipient_name.trim(),
            recipient_phone: address.recipient_phone.trim(),
            address_line1: address.address_line1.trim(),
            address_line2: address.address_line2.trim() || null,
            city: address.city.trim(),
            province: address.province.trim(),
            postal_code: address.postal_code.trim(),
          },
          credit_applied_cents: creditCents,
          otp_code: creditCents > 0 ? otpCode.trim() : null,
          payment_method: needsPaymentMethod ? paymentMethod : "BANK_TRANSFER",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const order: CjOrderRead = await res.json();
      setPlacedOrder(order);
      await queryClient.invalidateQueries({ queryKey: ["customer", "wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["customer", "orders"] });
      if (order.status === "PAID") {
        setStep("success");
        return;
      }
      if (order.payment_method === "CARD") {
        const returnUrl = window.location.href;
        const sessionRes = await fetch(
          `/api/proxy/cj/orders/mine/${order.id}/checkout-session?success_url=${encodeURIComponent(returnUrl)}&cancel_url=${encodeURIComponent(returnUrl)}`,
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

  const description = product.description || "";
  const longDescription = description.length > 280;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-3xl glass-card rounded-2xl border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[92vh] overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-6 py-4 border-b border-white/5 light:border-slate-200 bg-slate-950/95 light:bg-white/95 backdrop-blur">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wider text-orange-400">Marketplace 1</p>
            <h3 className="text-base font-bold text-white light:text-slate-900 truncate">
              {step === "product" ? product.name : step === "checkout" ? "Completa l'acquisto" : product.name}
            </h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 light:hover:bg-slate-900/10 text-slate-400 transition cursor-pointer" aria-label="Chiudi">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6">
          {step === "product" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-3">
                <div className="aspect-square rounded-2xl overflow-hidden border border-white/10 light:border-slate-200 bg-white">
                  <ProductThumbnail imageUrl={mainImage} alt={product.name} className="w-full h-full object-contain" />
                </div>
                {gallery.length > 1 && (
                  <div className="flex gap-2 overflow-x-auto pb-1">
                    {gallery.map((src, i) => (
                      <button
                        key={src}
                        type="button"
                        onClick={() => { setImageIndex(i); setImageOverride(null); }}
                        className={`w-14 h-14 shrink-0 rounded-lg overflow-hidden border-2 bg-white cursor-pointer transition ${
                          !imageOverride && i === imageIndex ? "border-orange-500" : "border-transparent opacity-70 hover:opacity-100"
                        }`}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element -- supplier images */}
                        <img src={src} alt="" className="w-full h-full object-cover" />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <div>
                  <h2 className="text-xl font-bold text-white light:text-slate-900 leading-snug">{product.name}</h2>
                  <p className="text-3xl font-extrabold text-white light:text-slate-900 mt-2 tabular-nums">
                    {euro((variant?.price_cents ?? product.min_price_cents) * quantity)}
                  </p>
                  <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">
                    {quantity > 1 && variant ? `${euro(variant.price_cents)} cad. · ` : ""}
                    {product.shipping_included ? "Spedizione inclusa" : "+ spedizione, calcolata al checkout"}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2 text-[11px]">
                  {product.shipping_days && (
                    <span className="px-2.5 py-1 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-400 font-semibold">
                      Consegna in {product.shipping_days} giorni
                    </span>
                  )}
                  {product.credit_discount_percentage > 0 && (
                    <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-semibold">
                      Paghi fino al {product.credit_discount_percentage}% in LialCash
                    </span>
                  )}
                </div>

                {product.variants.length > 1 && (
                  <div>
                    <p className="text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-2">Variante</p>
                    <div className="flex flex-wrap gap-2">
                      {product.variants.map((v) => (
                        <button
                          key={v.id}
                          type="button"
                          disabled={!v.in_stock}
                          onClick={() => { setVariantId(v.id); setImageOverride(v.image_url); }}
                          title={v.in_stock ? euro(v.price_cents) : "Non disponibile"}
                          className={`flex items-center gap-2 pl-1 pr-3 py-1 rounded-xl border text-xs font-semibold transition ${
                            !v.in_stock
                              ? "opacity-40 line-through cursor-not-allowed border-white/10 light:border-slate-300 text-slate-500"
                              : v.id === variantId
                                ? "cursor-pointer border-orange-500 bg-orange-500/10 text-white light:text-slate-900"
                                : "cursor-pointer border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:border-orange-500/50"
                          }`}
                        >
                          <span className="w-7 h-7 rounded-lg overflow-hidden bg-white shrink-0">
                            <ProductThumbnail imageUrl={v.image_url} alt="" className="w-full h-full object-cover" iconClassName="w-4 h-4 text-orange-400/40" />
                          </span>
                          {v.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <p className="text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-2">Quantità</p>
                  <div className="inline-flex items-center rounded-xl border border-white/10 light:border-slate-300 overflow-hidden">
                    <button type="button" onClick={() => changeQuantity(quantity - 1)} disabled={quantity <= 1} className="px-3.5 py-2 text-lg text-slate-300 light:text-slate-600 hover:bg-white/10 disabled:opacity-40 cursor-pointer">−</button>
                    <span className="w-10 text-center font-bold text-white light:text-slate-900 tabular-nums">{quantity}</span>
                    <button type="button" onClick={() => changeQuantity(quantity + 1)} disabled={quantity >= MAX_QUANTITY} className="px-3.5 py-2 text-lg text-slate-300 light:text-slate-600 hover:bg-white/10 disabled:opacity-40 cursor-pointer">+</button>
                  </div>
                </div>

                <button
                  type="button"
                  disabled={!variant || !variant.in_stock}
                  onClick={() => setStep("checkout")}
                  className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {variant && variant.in_stock ? "Acquista" : "Non disponibile"}
                </button>

                {description && (
                  <div className="pt-3 border-t border-white/5 light:border-slate-200">
                    <p className="text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1.5">Descrizione</p>
                    <p className={`text-xs text-slate-300 light:text-slate-600 whitespace-pre-line leading-relaxed ${!showFullDescription && longDescription ? "line-clamp-6" : ""}`}>
                      {description}
                    </p>
                    {longDescription && (
                      <button type="button" onClick={() => setShowFullDescription((v) => !v)} className="mt-1 text-[11px] font-semibold text-orange-400 hover:text-orange-300 cursor-pointer">
                        {showFullDescription ? "Mostra meno" : "Leggi tutto"}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {step === "checkout" && (
            <div className="space-y-4">
              <button type="button" onClick={() => setStep("product")} className="text-xs font-semibold text-orange-400 hover:text-orange-300 cursor-pointer">
                ← Torna al prodotto
              </button>

              <div className="flex items-center gap-3 p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
                <div className="w-14 h-14 rounded-lg overflow-hidden bg-white shrink-0">
                  <ProductThumbnail imageUrl={variant?.image_url ?? product.image_url} alt="" className="w-full h-full object-cover" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-white light:text-slate-900 truncate">{product.name}</p>
                  <p className="text-xs text-slate-400 light:text-slate-500">{variant?.label} · {quantity} {quantity === 1 ? "pezzo" : "pezzi"}</p>
                </div>
              </div>

              {quoteError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{(quoteError as Error).message}</div>
              )}
              {!quote && !quoteError && (
                <div className="py-10 text-center text-sm text-slate-500">Calcolo della spedizione in corso...</div>
              )}

              {quote && (
                <>
                  <Section n={1} title="Dove lo spediamo?" done={addressComplete}>
                    <div className="grid grid-cols-1 sm:grid-cols-6 gap-3">
                      <Field label="Nome e cognome" className="sm:col-span-3">
                        <input className={inputClass} value={address.recipient_name} maxLength={50} autoComplete="name"
                          onChange={(e) => setAddress({ ...address, recipient_name: e.target.value })} />
                      </Field>
                      <Field label="Telefono (per il corriere)" className="sm:col-span-3">
                        <input className={inputClass} value={address.recipient_phone} maxLength={20} inputMode="tel" autoComplete="tel"
                          onChange={(e) => setAddress({ ...address, recipient_phone: e.target.value })} />
                      </Field>
                      <Field label="Indirizzo e numero civico" className="sm:col-span-4">
                        <input className={inputClass} value={address.address_line1} maxLength={255} autoComplete="address-line1"
                          onChange={(e) => setAddress({ ...address, address_line1: e.target.value })} />
                      </Field>
                      <Field label="Scala, interno (facoltativo)" className="sm:col-span-2">
                        <input className={inputClass} value={address.address_line2} maxLength={255} autoComplete="address-line2"
                          onChange={(e) => setAddress({ ...address, address_line2: e.target.value })} />
                      </Field>
                      <Field label="CAP" className="sm:col-span-2">
                        <input className={inputClass} value={address.postal_code} maxLength={12} inputMode="numeric" autoComplete="postal-code"
                          onChange={(e) => setAddress({ ...address, postal_code: e.target.value })} />
                      </Field>
                      <Field label="Città" className="sm:col-span-3">
                        <input className={inputClass} value={address.city} maxLength={50} autoComplete="address-level2"
                          onChange={(e) => setAddress({ ...address, city: e.target.value })} />
                      </Field>
                      <Field label="Provincia" className="sm:col-span-1">
                        <input className={inputClass} value={address.province} maxLength={50} placeholder="MI"
                          onChange={(e) => setAddress({ ...address, province: e.target.value.toUpperCase() })} />
                      </Field>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Spedizione in Italia{quote.shipping_days ? ` · consegna stimata in ${quote.shipping_days} giorni lavorativi` : ""}.
                    </p>
                  </Section>

                  {quote.max_creditable_cents > 0 && maxUsableCents > 0 && (
                    <Section n={2} title="Vuoi usare i tuoi LialCash?" done={creditCents > 0 && !!otpCode.trim()}>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => { const next = !useCredit; setUseCredit(next); setCreditAmount(next ? (maxUsableCents / 100).toFixed(2) : "0.00"); resetOtp(); }}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                            useCredit ? "bg-orange-600 border-orange-600 text-white" : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600"
                          }`}
                        >
                          {useCredit ? "Sì, uso i LialCash" : "Usa i LialCash"}
                        </button>
                        <span className="text-[11px] text-slate-500">
                          Saldo {lialCash(quote.customer_wallet_balance_cents)} · qui fino a {lialCash(maxUsableCents)}
                        </span>
                      </div>
                      {useCredit && (
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            {[0.25, 0.5, 1].map((f) => (
                              <button key={f} type="button"
                                onClick={() => { setCreditAmount(((Math.round(maxUsableCents * f)) / 100).toFixed(2)); resetOtp(); }}
                                className="px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10 cursor-pointer">
                                {f === 1 ? "Massimo" : `${f * 100}%`}
                              </button>
                            ))}
                            <input inputMode="decimal" value={creditAmount}
                              onChange={(e) => { setCreditAmount(e.target.value); resetOtp(); }}
                              className="w-28 rounded-lg glass-input px-3 py-1.5 text-sm" />
                            <span className="text-xs text-slate-500">LialCash</span>
                          </div>
                          {creditCents > 0 && (
                            !otpRequested ? (
                              <button type="button" onClick={handleRequestOtp} disabled={otpRequesting}
                                className="px-4 py-2 rounded-lg bg-orange-600/15 hover:bg-orange-600/25 border border-orange-500/30 text-xs font-semibold text-orange-400 transition cursor-pointer disabled:opacity-50">
                                {otpRequesting ? "Invio in corso..." : "Conferma con il codice via email"}
                              </button>
                            ) : (
                              <div className="flex flex-wrap items-center gap-2">
                                <input inputMode="numeric" autoFocus value={otpCode} onChange={(e) => setOtpCode(e.target.value)}
                                  placeholder="Codice ricevuto via email"
                                  className="w-full max-w-[200px] rounded-lg glass-input px-3 py-2 text-sm font-mono tracking-wider" />
                                <button type="button" onClick={handleRequestOtp} disabled={otpRequesting}
                                  className="text-[11px] font-semibold text-orange-400 hover:text-orange-300 cursor-pointer disabled:opacity-50">Rinvia</button>
                              </div>
                            )
                          )}
                          {otpError && <p className="text-[11px] text-rose-400">{otpError}</p>}
                        </div>
                      )}
                    </Section>
                  )}

                  {needsPaymentMethod && (
                    <Section n={quote.max_creditable_cents > 0 && maxUsableCents > 0 ? 3 : 2} title="Come vuoi pagare?" done={!!paymentMethod}>
                      {noMethodAvailable ? (
                        <p className="text-xs text-rose-400">Nessun metodo di pagamento disponibile. Contatta l&apos;assistenza.</p>
                      ) : (
                        <div className="flex gap-2.5">
                          {quote.bank_transfer_available && (
                            <button type="button" onClick={() => setPaymentMethod("BANK_TRANSFER")}
                              className={`flex-1 px-3 py-3 rounded-xl text-sm font-semibold border-2 transition cursor-pointer ${
                                paymentMethod === "BANK_TRANSFER" ? "bg-orange-600 border-orange-600 text-white" : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600"
                              }`}>
                              Bonifico
                            </button>
                          )}
                          {quote.card_available && (
                            <button type="button" onClick={() => setPaymentMethod("CARD")}
                              className={`flex-1 px-3 py-3 rounded-xl text-sm font-semibold border-2 transition cursor-pointer ${
                                paymentMethod === "CARD" ? "bg-orange-600 border-orange-600 text-white" : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600"
                              }`}>
                              Carta
                            </button>
                          )}
                        </div>
                      )}
                    </Section>
                  )}

                  <div className="p-4 rounded-xl bg-gradient-to-br from-orange-600/10 to-amber-500/5 border border-orange-500/20 space-y-1.5 text-xs">
                    <div className="flex justify-between text-slate-400 light:text-slate-500">
                      <span>{quote.quantity} × {euro(quote.unit_price_cents)}</span><span>{euro(quote.items_cents)}</span>
                    </div>
                    <div className="flex justify-between text-slate-400 light:text-slate-500">
                      <span>Spedizione</span><span>{quote.shipping_included || quote.shipping_cents === 0 ? "Inclusa" : euro(quote.shipping_cents)}</span>
                    </div>
                    {creditCents > 0 && (
                      <div className="flex justify-between text-emerald-400">
                        <span>LialCash usati</span><span>-{lialCash(creditCents)}</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between pt-1.5 border-t border-white/10 light:border-slate-300">
                      <span className="text-sm font-bold text-white light:text-slate-900">Totale da pagare</span>
                      <span className={`text-xl font-extrabold tabular-nums ${residualCents > 0 ? "text-orange-400" : "text-emerald-400"}`}>
                        {quoteLoading ? "…" : euro(Math.max(residualCents, 0))}
                      </span>
                    </div>
                  </div>

                  {submitError && (
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{submitError}</div>
                  )}

                  <button
                    onClick={handleConfirm}
                    disabled={
                      submitLoading || !addressComplete || quoteLoading
                      || (needsPaymentMethod && (noMethodAvailable || !paymentMethod))
                      || (creditCents > 0 && !otpCode.trim())
                    }
                    className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {submitLoading ? "Elaborazione..." : residualCents > 0 ? "Conferma e paga" : "Conferma ordine"}
                  </button>
                  {!addressComplete && (
                    <p className="text-[11px] text-slate-500 text-center">Completa l&apos;indirizzo di spedizione per continuare.</p>
                  )}
                </>
              )}
            </div>
          )}

          {step === "success" && placedOrder && (
            <div className="text-center py-8 space-y-3">
              <p className="text-4xl">🎉</p>
              <p className="text-sm text-slate-300 light:text-slate-600">
                Ordine confermato, pagato con i tuoi LialCash. Ti avvisiamo appena parte: lo segui da &ldquo;I miei Ordini&rdquo;.
              </p>
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer">Chiudi</button>
            </div>
          )}

          {step === "card_redirect" && placedOrder && (
            <div className="text-center py-8 space-y-3">
              <p className="text-sm text-slate-300 light:text-slate-600">
                Abbiamo aperto il pagamento con carta in una nuova scheda: <strong className="text-orange-400">{euro(placedOrder.residual_amount_cents)}</strong>.
              </p>
              <p className="text-xs text-slate-500">L&apos;ordine è anche in &ldquo;I miei Ordini&rdquo;, dove puoi pagarlo e seguirne la spedizione.</p>
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer">Chiudi</button>
            </div>
          )}

          {step === "bank_instructions" && placedOrder && (
            <div className="space-y-3">
              <p className="text-sm text-slate-300 light:text-slate-600">
                Ordine creato. Paga <strong className="text-orange-400">{euro(placedOrder.residual_amount_cents)}</strong> con bonifico: lo spediamo appena riceviamo il pagamento.
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
                <p className="pt-1"><span className="text-slate-500">Causale:</span> <span className="font-mono text-orange-400">Ordine {placedOrder.id.slice(0, 8).toUpperCase()}</span></p>
              </div>
              <button onClick={onClose} className="w-full px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer">Ho capito</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
