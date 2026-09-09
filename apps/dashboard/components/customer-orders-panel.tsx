"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ProductThumbnail } from "@/components/product-thumbnail";
import { friendlyApiError } from "@/lib/api-error";
import type { OrderRead } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  AWAITING_PAYMENT: "In attesa di pagamento",
  PAID: "Pagato",
  CANCELLED: "Annullato",
};
const STATUS_COLORS: Record<string, string> = {
  AWAITING_PAYMENT: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  PAID: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  CANCELLED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};
const PAYMENT_METHOD_LABELS: Record<string, string> = {
  BANK_TRANSFER: "Bonifico",
  CARD: "Carta (Stripe)",
};

type OrderFilter = "ALL" | "PAID" | "AWAITING_PAYMENT" | "CANCELLED" | "BANK_TRANSFER" | "CARD";

const FILTER_TABS: { key: OrderFilter; label: string }[] = [
  { key: "ALL", label: "Tutti" },
  { key: "PAID", label: "Pagati" },
  { key: "AWAITING_PAYMENT", label: "In attesa" },
  { key: "CANCELLED", label: "Annullati" },
  { key: "BANK_TRANSFER", label: "Bonifico" },
  { key: "CARD", label: "Carta" },
];

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" });
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Short, human-typeable reference for an order -- there is no dedicated
    sequential order number in the schema, so (like the bank-transfer
    causale already did) this is derived consistently from the UUID
    everywhere an order needs to be identified at a glance: here, in
    admin-orders-panel.tsx, and in the "Pagamento confermato" email. */
function orderCode(id: string): string {
  return id.slice(0, 8).toUpperCase();
}

async function fetchMyOrders(): Promise<OrderRead[]> {
  const res = await fetch("/api/proxy/orders/mine");
  if (!res.ok) throw new Error("Impossibile caricare i tuoi ordini.");
  return res.json();
}

async function fetchPaymentInfo(): Promise<{ iban: string | null; holder: string; instructions: string | null }> {
  const res = await fetch("/api/proxy/invoice-redemptions/payment-info");
  if (!res.ok) throw new Error("Impossibile caricare le coordinate di pagamento.");
  return res.json();
}

function OrderDetailModal({ order, onClose, onViewProof, viewProofLoading }: {
  order: OrderRead;
  onClose: () => void;
  onViewProof: () => void;
  viewProofLoading: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-lg max-h-[85vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-14 h-14 rounded-xl overflow-hidden shrink-0 border border-white/10 light:border-slate-200">
              <ProductThumbnail imageUrl={order.product_image_url} alt={order.product_name} iconClassName="w-6 h-6 text-orange-400/40" />
            </div>
            <div className="min-w-0">
              <h3 className="text-lg font-bold text-white light:text-slate-900 truncate">{order.product_name}</h3>
              <p className="text-xs text-slate-500">Ordine <span className="font-mono text-slate-400 light:text-slate-600">#{orderCode(order.id)}</span></p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition cursor-pointer shrink-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex items-center gap-2 mb-5 flex-wrap">
          <span className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${STATUS_COLORS[order.status]}`}>
            {STATUS_LABELS[order.status]}
          </span>
          <span className="px-2.5 py-1 rounded-full text-[11px] font-bold border bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600">
            {PAYMENT_METHOD_LABELS[order.payment_method] ?? order.payment_method}
          </span>
        </div>

        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3 p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200">
            <div>
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Totale</p>
              <p className="font-bold text-white light:text-slate-900">{euro(order.amount_cents)}</p>
            </div>
            {order.credit_applied_cents > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Crediti applicati</p>
                <p className="font-bold text-emerald-400">-{euro(order.credit_applied_cents)}</p>
              </div>
            )}
            {order.status === "AWAITING_PAYMENT" && (
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Residuo da pagare</p>
                <p className="font-bold text-amber-400">{euro(order.residual_amount_cents)}</p>
              </div>
            )}
          </div>

          <div className="space-y-1.5 text-xs text-slate-400 light:text-slate-500">
            <p>Ordinato il <span className="text-slate-200 light:text-slate-800">{formatDateTime(order.created_at)}</span></p>
            {order.paid_at && <p>Pagato il <span className="text-emerald-400">{formatDateTime(order.paid_at)}</span></p>}
            {order.cancelled_at && (
              <p>Annullato il <span className="text-rose-400">{formatDateTime(order.cancelled_at)}</span>{order.cancellation_reason && ` -- ${order.cancellation_reason}`}</p>
            )}
            {order.payment_method === "CARD" && order.stripe_checkout_session_id && (
              <p className="break-all">ID sessione Stripe: <span className="font-mono text-slate-300 light:text-slate-700">{order.stripe_checkout_session_id}</span></p>
            )}
            {order.payment_method === "BANK_TRANSFER" && (
              <p>Causale bonifico: <span className="font-mono text-orange-400">Ordine {orderCode(order.id)}</span></p>
            )}
          </div>

          {order.payment_proof_uploaded_at && (
            <button
              onClick={onViewProof}
              disabled={viewProofLoading}
              className="w-full px-4 py-2 rounded-xl bg-sky-600/10 hover:bg-sky-600/20 border border-sky-500/20 text-sky-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
            >
              {viewProofLoading ? "..." : `Vedi la prova di pagamento caricata il ${formatDate(order.payment_proof_uploaded_at)}`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** "I miei ordini": every DROPSHIPPING/PARTNER product purchase the customer
    has made, like an e-commerce order-history page -- a professional shop
    always lets the buyer see what they bought and its status, and pay an
    unpaid order without having to remember to go back to the product page.
    Never shows Lial Energy contracts (see business-rules.md -- those are
    Contract rows, not Order rows, tracked in "I miei Contratti" instead). */
export function CustomerOrdersPanel() {
  const queryClient = useQueryClient();
  const { data: orders, isLoading, error } = useQuery({
    queryKey: ["customer", "orders", "mine"],
    queryFn: fetchMyOrders,
  });
  const [filter, setFilter] = useState<OrderFilter>("ALL");
  const [payingId, setPayingId] = useState<string | null>(null);
  const [payError, setPayError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [bankDetailsFor, setBankDetailsFor] = useState<string | null>(null);
  const [switchingId, setSwitchingId] = useState<string | null>(null);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [proofOrderId, setProofOrderId] = useState<string | null>(null);
  const [detailOrderId, setDetailOrderId] = useState<string | null>(null);
  const [viewProofLoading, setViewProofLoading] = useState(false);
  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: bankDetailsFor !== null,
  });

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["customer", "orders"] });
  }

  async function startCardCheckout(order: OrderRead) {
    setPayingId(order.id);
    try {
      // Opens Stripe in a NEW TAB rather than navigating away from the
      // dashboard -- if the payment fails or the customer just changes their
      // mind, this tab (and whatever they were doing in it) is never lost.
      // success_url lands back on "I miei Ordini" with a banner (see
      // customer-client-page.tsx) instead of a bare dashboard reload.
      const returnUrl = new URL("/customer", window.location.origin);
      returnUrl.searchParams.set("tab", "orders");
      const successUrl = new URL(returnUrl);
      successUrl.searchParams.set("payment", "success");
      successUrl.searchParams.set("order_id", order.id);
      const cancelUrl = new URL(returnUrl);
      cancelUrl.searchParams.set("payment", "cancelled");

      const res = await fetch(
        `/api/proxy/orders/mine/${order.id}/checkout-session?success_url=${encodeURIComponent(successUrl.toString())}&cancel_url=${encodeURIComponent(cancelUrl.toString())}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { checkout_url } = await res.json();
      window.open(checkout_url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setPayError(err.message || "Impossibile avviare il pagamento.");
    } finally {
      setPayingId(null);
    }
  }

  function handlePay(order: OrderRead) {
    setPayError(null);
    if (order.payment_method === "BANK_TRANSFER") {
      setBankDetailsFor(bankDetailsFor === order.id ? null : order.id);
      return;
    }
    startCardCheckout(order);
  }

  async function handleSwitchMethod(order: OrderRead, newMethod: "CARD" | "BANK_TRANSFER") {
    setActionError(null);
    setSwitchingId(order.id);
    try {
      const res = await fetch(`/api/proxy/orders/mine/${order.id}/payment-method`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payment_method: newMethod }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const updated: OrderRead = await res.json();
      await invalidate();
      if (newMethod === "CARD") {
        // Straight into checkout -- "pagalo subito con carta" should not
        // need a second click once the method is switched.
        await startCardCheckout(updated);
      } else {
        setBankDetailsFor(order.id);
      }
    } catch (err: any) {
      setActionError(err.message || "Impossibile cambiare il metodo di pagamento.");
    } finally {
      setSwitchingId(null);
    }
  }

  function openProofPicker(orderId: string) {
    setActionError(null);
    setProofOrderId(orderId);
    fileInputRef.current?.click();
  }

  async function handleProofSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file || !proofOrderId) return;
    setUploadingId(proofOrderId);
    setActionError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`/api/proxy/orders/mine/${proofOrderId}/payment-proof`, { method: "POST", body });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await invalidate();
    } catch (err: any) {
      setActionError(err.message || "Impossibile caricare la prova di pagamento.");
    } finally {
      setUploadingId(null);
      setProofOrderId(null);
    }
  }

  async function handleViewProof(orderId: string) {
    setViewProofLoading(true);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/orders/mine/${orderId}/payment-proof-url`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setActionError(err.message || "Impossibile aprire la prova di pagamento.");
    } finally {
      setViewProofLoading(false);
    }
  }

  if (isLoading) {
    return <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 animate-pulse h-40" />;
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
        Impossibile caricare i tuoi ordini.
      </div>
    );
  }

  const list = orders ?? [];

  if (list.length === 0) {
    return (
      <div className="glass-card rounded-2xl p-12 text-center border-white/5 light:border-slate-200">
        <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
        </svg>
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Nessun ordine ancora</h3>
        <p className="text-sm text-slate-400 light:text-slate-500 mt-1">
          I prodotti che acquisti dallo Shop compaiono qui, con lo stato del pagamento.
        </p>
      </div>
    );
  }

  const filteredList = list.filter((o) => {
    if (filter === "ALL") return true;
    if (filter === "BANK_TRANSFER" || filter === "CARD") return o.payment_method === filter;
    return o.status === filter;
  });
  const detailOrder = detailOrderId ? list.find((o) => o.id === detailOrderId) ?? null : null;

  return (
    <div className="space-y-4">
      <input ref={fileInputRef} type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={handleProofSelected} />

      <div className="flex flex-wrap gap-2">
        {FILTER_TABS.map((tab) => {
          const count = tab.key === "ALL"
            ? list.length
            : list.filter((o) => (tab.key === "BANK_TRANSFER" || tab.key === "CARD" ? o.payment_method === tab.key : o.status === tab.key)).length;
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

      {payError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{payError}</div>
      )}
      {actionError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{actionError}</div>
      )}

      {filteredList.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-10">Nessun ordine in questa categoria.</p>
      ) : (
        filteredList.map((o) => {
          const awaiting = o.status === "AWAITING_PAYMENT";
          const busy = payingId === o.id || switchingId === o.id || uploadingId === o.id;
          return (
            <div key={o.id} className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 p-5">
              <div className="flex flex-wrap items-start gap-4">
                <button
                  type="button"
                  onClick={() => setDetailOrderId(o.id)}
                  className="w-16 h-16 rounded-xl overflow-hidden shrink-0 border border-white/10 light:border-slate-200 cursor-pointer"
                  title="Vedi dettagli ordine"
                >
                  <ProductThumbnail imageUrl={o.product_image_url} alt={o.product_name} iconClassName="w-7 h-7 text-orange-400/40" />
                </button>
                <div className="flex-1 min-w-[180px]">
                  <div className="flex items-center gap-2 flex-wrap">
                    <button
                      type="button"
                      onClick={() => setDetailOrderId(o.id)}
                      className="font-semibold text-white light:text-slate-900 hover:text-orange-400 transition cursor-pointer text-left"
                    >
                      {o.product_name}
                    </button>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[o.status]}`}>
                      {STATUS_LABELS[o.status]}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    Ordine <span className="font-mono text-slate-400 light:text-slate-600">#{orderCode(o.id)}</span> · Ordinato il {formatDate(o.created_at)}
                  </p>
                  <div className="flex items-center gap-3 mt-2 text-xs flex-wrap">
                    <span className="text-slate-400 light:text-slate-500">Totale <strong className="text-white light:text-slate-900">{euro(o.amount_cents)}</strong></span>
                    {o.credit_applied_cents > 0 && (
                      <span className="text-emerald-400">-{euro(o.credit_applied_cents)} crediti</span>
                    )}
                    {awaiting && (
                      <span className="text-amber-400">Residuo {euro(o.residual_amount_cents)}</span>
                    )}
                    <button
                      type="button"
                      onClick={() => setDetailOrderId(o.id)}
                      className="text-orange-400 hover:text-orange-300 font-semibold cursor-pointer"
                    >
                      Dettagli →
                    </button>
                  </div>
                  {o.cancellation_reason && (
                    <p className="text-[11px] text-rose-400 mt-1">Motivo annullamento: {o.cancellation_reason}</p>
                  )}
                </div>

                {awaiting && (
                  <div className="flex flex-col gap-2 w-full sm:w-52 shrink-0">
                    <button
                      onClick={() => handlePay(o)}
                      disabled={busy}
                      className="w-full px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                    >
                      {payingId === o.id ? "Apertura Stripe..." : o.payment_method === "CARD" ? "Paga con carta" : "Vedi coordinate bonifico"}
                    </button>
                    {o.payment_method === "BANK_TRANSFER" ? (
                      <>
                        <button
                          onClick={() => handleSwitchMethod(o, "CARD")}
                          disabled={busy}
                          className="w-full px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                        >
                          {switchingId === o.id ? "..." : "Paga subito con carta"}
                        </button>
                        <button
                          onClick={() => openProofPicker(o.id)}
                          disabled={busy}
                          className="w-full px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                        >
                          {uploadingId === o.id
                            ? "Caricamento..."
                            : o.payment_proof_uploaded_at
                              ? "Sostituisci prova di pagamento"
                              : "Aggiungi prova di pagamento"}
                        </button>
                        {o.payment_proof_uploaded_at && (
                          <p className="text-[10px] text-emerald-400 text-center">
                            ✓ Prova caricata il {formatDate(o.payment_proof_uploaded_at)}
                          </p>
                        )}
                      </>
                    ) : (
                      <button
                        onClick={() => handleSwitchMethod(o, "BANK_TRANSFER")}
                        disabled={busy}
                        className="w-full px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                      >
                        {switchingId === o.id ? "..." : "Paga con bonifico invece"}
                      </button>
                    )}
                  </div>
                )}
              </div>

              {bankDetailsFor === o.id && (
                <div className="mt-4 pt-4 border-t border-white/5 light:border-slate-200 p-4 rounded-xl bg-white/5 light:bg-slate-900/5 text-xs space-y-1.5">
                  {paymentInfo?.iban ? (
                    <>
                      <p><span className="text-slate-500">IBAN:</span> <span className="font-mono">{paymentInfo.iban}</span></p>
                      <p><span className="text-slate-500">Intestatario:</span> {paymentInfo.holder}</p>
                      {paymentInfo.instructions && <p className="text-slate-400 light:text-slate-500 pt-1">{paymentInfo.instructions}</p>}
                    </>
                  ) : (
                    <p className="text-slate-500">Contatta l&apos;amministrazione per le coordinate bancarie.</p>
                  )}
                  <p className="pt-1"><span className="text-slate-500">Causale consigliata:</span> <span className="font-mono text-orange-400">Ordine {orderCode(o.id)}</span></p>
                </div>
              )}
            </div>
          );
        })
      )}

      {detailOrder && (
        <OrderDetailModal
          order={detailOrder}
          onClose={() => setDetailOrderId(null)}
          onViewProof={() => handleViewProof(detailOrder.id)}
          viewProofLoading={viewProofLoading}
        />
      )}
    </div>
  );
}
