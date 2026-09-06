"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" });
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

/** "I miei ordini": every DROPSHIPPING/PARTNER product purchase the customer
    has made, like an e-commerce order-history page -- a professional shop
    always lets the buyer see what they bought and its status, and pay an
    unpaid order without having to remember to go back to the product page.
    Never shows Lial Energy contracts (see business-rules.md -- those are
    Contract rows, not Order rows, tracked in "I miei Contratti" instead). */
export function CustomerOrdersPanel() {
  const { data: orders, isLoading, error } = useQuery({
    queryKey: ["customer", "orders", "mine"],
    queryFn: fetchMyOrders,
  });
  const [payingId, setPayingId] = useState<string | null>(null);
  const [payError, setPayError] = useState<string | null>(null);
  const [bankDetailsFor, setBankDetailsFor] = useState<string | null>(null);
  const { data: paymentInfo } = useQuery({
    queryKey: ["customer", "payment-info"],
    queryFn: fetchPaymentInfo,
    enabled: bankDetailsFor !== null,
  });

  async function handlePay(order: OrderRead) {
    setPayError(null);
    if (order.payment_method === "BANK_TRANSFER") {
      setBankDetailsFor(bankDetailsFor === order.id ? null : order.id);
      return;
    }
    setPayingId(order.id);
    try {
      // Opens Stripe in a NEW TAB rather than navigating away from the
      // dashboard -- if the payment fails or the customer just changes their
      // mind, this tab (and whatever they were doing in it) is never lost.
      const returnUrl = `${window.location.origin}/customer`;
      const res = await fetch(
        `/api/proxy/orders/mine/${order.id}/checkout-session?success_url=${encodeURIComponent(returnUrl)}&cancel_url=${encodeURIComponent(returnUrl)}`,
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

  return (
    <div className="space-y-4">
      {payError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{payError}</div>
      )}
      {list.map((o) => (
        <div key={o.id} className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 p-5">
          <div className="flex flex-wrap items-start gap-4">
            <div className="w-16 h-16 rounded-xl overflow-hidden shrink-0 border border-white/10 light:border-slate-200">
              <ProductThumbnail imageUrl={o.product_image_url} alt={o.product_name} iconClassName="w-7 h-7 text-orange-400/40" />
            </div>
            <div className="flex-1 min-w-[180px]">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-white light:text-slate-900">{o.product_name}</h4>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[o.status]}`}>
                  {STATUS_LABELS[o.status]}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">Ordinato il {formatDate(o.created_at)}</p>
              <div className="flex items-center gap-3 mt-2 text-xs">
                <span className="text-slate-400 light:text-slate-500">Totale <strong className="text-white light:text-slate-900">{euro(o.amount_cents)}</strong></span>
                {o.credit_applied_cents > 0 && (
                  <span className="text-emerald-400">-{euro(o.credit_applied_cents)} crediti</span>
                )}
                {o.status === "AWAITING_PAYMENT" && (
                  <span className="text-amber-400">Residuo {euro(o.residual_amount_cents)}</span>
                )}
              </div>
              {o.cancellation_reason && (
                <p className="text-[11px] text-rose-400 mt-1">Motivo annullamento: {o.cancellation_reason}</p>
              )}
            </div>
            {o.status === "AWAITING_PAYMENT" && (
              <button
                onClick={() => handlePay(o)}
                disabled={payingId === o.id}
                className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-xs font-semibold transition cursor-pointer disabled:opacity-50 shrink-0"
              >
                {payingId === o.id ? "..." : o.payment_method === "CARD" ? "Paga con carta" : "Vedi coordinate bonifico"}
              </button>
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
              <p className="pt-1"><span className="text-slate-500">Causale consigliata:</span> <span className="font-mono text-orange-400">Ordine {o.id.slice(0, 8)}</span></p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
