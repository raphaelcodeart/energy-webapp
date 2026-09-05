"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { CustomerRead, OrderQuoteRead, OrderRead, ProductCatalogRead } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  AWAITING_PAYMENT: "Attesa bonifico residuo",
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

async function fetchCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

async function fetchOrders(statusFilter: string): Promise<OrderRead[]> {
  const qs = statusFilter !== "ALL" ? `?status_filter=${statusFilter}` : "";
  const res = await fetch(`/api/proxy/orders${qs}`);
  if (!res.ok) throw new Error("Impossibile caricare gli ordini.");
  return res.json();
}

async function fetchQuote(customerUserId: string, productVersionId: string): Promise<OrderQuoteRead> {
  const res = await fetch(`/api/proxy/orders/quote?customer_user_id=${customerUserId}&product_version_id=${productVersionId}`);
  if (!res.ok) throw new Error("Impossibile calcolare il preventivo.");
  return res.json();
}

/** Checkout per prodotti dropshipping/partner (Fase 4 del progetto cashback,
    vedi docs/cashback-partner-invoices-plan.md) -- MAI per prodotti Interno
    Lial Energy, che restano contratti (vedi "Nuovo Contratto"). Solo admin
    per ora: nessun self-checkout cliente. */
export function AdminOrdersPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("AWAITING_PAYMENT");
  const [showCreate, setShowCreate] = useState(false);
  const [customerUserId, setCustomerUserId] = useState("");
  const [productVersionId, setProductVersionId] = useState("");
  const [creditAmount, setCreditAmount] = useState("0.00");
  const [note, setNote] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState("");

  const { data: customers } = useQuery({ queryKey: ["admin", "customers"], queryFn: fetchCustomers });
  const { data: allProducts } = useQuery({ queryKey: ["admin", "products"], queryFn: fetchProducts });
  const { data: orders, error: loadError } = useQuery({
    queryKey: ["admin", "orders", statusFilter],
    queryFn: () => fetchOrders(statusFilter),
  });

  const orderableCustomers = (customers ?? []).filter((c) => !!c.user_id);
  const orderableProducts = (allProducts ?? []).filter((p) => p.category !== "INTERNAL" && p.current_version);

  const { data: quote } = useQuery({
    queryKey: ["admin", "orders", "quote", customerUserId, productVersionId],
    queryFn: () => fetchQuote(customerUserId, productVersionId),
    enabled: !!customerUserId && !!productVersionId,
  });

  // Default the credit field to the maximum usable amount whenever the
  // quote changes, so the common case ("use all available credit") needs
  // no typing -- the admin only has to lower it if they want less applied.
  useEffect(() => {
    if (!quote) return;
    const maxUsable = Math.min(quote.max_creditable_cents, quote.customer_wallet_balance_cents);
    setCreditAmount((maxUsable / 100).toFixed(2));
  }, [quote]);

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "orders"] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "wallets"] });
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const creditCents = Math.round(parseFloat(creditAmount.replace(",", ".")) * 100);
    if (!Number.isFinite(creditCents) || creditCents < 0) {
      setCreateError("Importo in crediti non valido.");
      return;
    }
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_user_id: customerUserId,
          product_version_id: productVersionId,
          credit_applied_cents: creditCents,
          note: note || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCreate(false);
      setCustomerUserId("");
      setProductVersionId("");
      setCreditAmount("0.00");
      setNote("");
      await invalidate();
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare l'ordine.");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleConfirmPayment(id: string) {
    setActionLoadingId(id);
    try {
      const res = await fetch(`/api/proxy/orders/${id}/confirm-payment`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await invalidate();
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleCancel(id: string) {
    if (!cancelReason.trim()) return;
    setActionLoadingId(id);
    try {
      const res = await fetch(`/api/proxy/orders/${id}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: cancelReason.trim() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setCancellingId(null);
      setCancelReason("");
      await invalidate();
    } finally {
      setActionLoadingId(null);
    }
  }

  const residualPreview = quote
    ? quote.amount_cents - Math.min(
        Math.round((parseFloat(creditAmount.replace(",", ".")) || 0) * 100),
        quote.max_creditable_cents,
        quote.customer_wallet_balance_cents
      )
    : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-slate-400 light:text-slate-500">
          Acquisti di prodotti dropshipping/partner, con sconto in crediti opzionale.
        </p>
        <button
          onClick={() => { setShowCreate(!showCreate); setCreateError(null); }}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
        >
          {showCreate ? "Annulla" : "+ Nuovo Ordine"}
        </button>
      </div>

      {showCreate && (
        <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cliente</label>
                <select required value={customerUserId} onChange={(e) => setCustomerUserId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                  <option value="">Seleziona...</option>
                  {orderableCustomers.map((c) => (
                    <option key={c.id} value={c.user_id!}>{c.display_name}</option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-500">Solo clienti con un account collegato compaiono qui.</p>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Prodotto</label>
                <select required value={productVersionId} onChange={(e) => setProductVersionId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                  <option value="">Seleziona...</option>
                  {orderableProducts.map((p) => (
                    <option key={p.id} value={p.current_version!.id}>
                      {p.current_version!.name} ({euro(p.current_version!.base_price_cents)})
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-500">Solo prodotti dropshipping/partner -- i prodotti Interno Lial si vendono come contratto.</p>
              </div>
            </div>

            {quote && (
              <div className="p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200 space-y-3">
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase">Prezzo prodotto</p>
                    <p className="font-semibold text-white light:text-slate-900">{euro(quote.amount_cents)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase">Sconto max in crediti</p>
                    <p className="font-semibold text-orange-400">{quote.credit_discount_percentage}% ({euro(quote.max_creditable_cents)})</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase">Saldo cliente</p>
                    <p className="font-semibold text-white light:text-slate-900">{euro(quote.customer_wallet_balance_cents)}</p>
                  </div>
                </div>
                <div className="space-y-1 pt-2 border-t border-white/5 light:border-slate-200">
                  <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Crediti da applicare (EUR)</label>
                  <input
                    inputMode="decimal"
                    value={creditAmount}
                    onChange={(e) => setCreditAmount(e.target.value)}
                    className="w-full max-w-[160px] rounded-lg glass-input px-3 py-1.5 text-sm focus:border-orange-500"
                  />
                </div>
                {residualPreview != null && (
                  <p className="text-xs text-slate-300 light:text-slate-600">
                    Residuo da bonifico: <strong className="text-orange-400">{euro(Math.max(residualPreview, 0))}</strong>
                    {residualPreview <= 0 && <span className="text-emerald-400"> -- copre l'intero importo, nessun bonifico necessario</span>}
                  </p>
                )}
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nota (opzionale)</label>
              <input value={note} onChange={(e) => setNote(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
            </div>

            <button type="submit" disabled={createLoading || !quote}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
              {createLoading ? "Creazione..." : "Crea Ordine"}
            </button>
            {createError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
            )}
          </form>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {["AWAITING_PAYMENT", "PAID", "CANCELLED", "ALL"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
              statusFilter === s
                ? "bg-orange-600 border-orange-600 text-white"
                : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
            }`}
          >
            {s === "ALL" ? "Tutti" : STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare gli ordini.</p>}

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 divide-y divide-white/5 light:divide-slate-200 overflow-hidden">
        {orders === undefined ? (
          <p className="text-center py-8 text-slate-500 text-sm">Caricamento...</p>
        ) : orders.length === 0 ? (
          <p className="text-center py-8 text-slate-500 text-sm">Nessun ordine in questo stato.</p>
        ) : (
          orders.map((o) => (
            <div key={o.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-white light:text-slate-900">{o.customer_display_name}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[o.status]}`}>
                      {STATUS_LABELS[o.status]}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">
                    {o.product_name} · Totale {euro(o.amount_cents)}
                    {o.credit_applied_cents > 0 && <> · Crediti {euro(o.credit_applied_cents)}</>}
                    {" "}· Residuo {euro(o.residual_amount_cents)}
                  </p>
                  {o.cancellation_reason && (
                    <p className="text-[11px] text-rose-400 mt-1">Motivo annullamento: {o.cancellation_reason}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-wrap justify-end">
                  {o.status === "AWAITING_PAYMENT" && (
                    <>
                      <button
                        onClick={() => handleConfirmPayment(o.id)}
                        disabled={actionLoadingId === o.id}
                        className="px-2.5 py-1.5 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                      >
                        {actionLoadingId === o.id ? "..." : "Conferma bonifico ricevuto"}
                      </button>
                      <button
                        onClick={() => setCancellingId(cancellingId === o.id ? null : o.id)}
                        className="px-2.5 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer"
                      >
                        Annulla
                      </button>
                    </>
                  )}
                </div>
              </div>
              {cancellingId === o.id && (
                <div className="mt-3 pt-3 border-t border-white/5 light:border-slate-200 flex items-end gap-2">
                  <div className="space-y-1 flex-1 max-w-sm">
                    <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Motivo annullamento</label>
                    <input autoFocus value={cancelReason} onChange={(e) => setCancelReason(e.target.value)}
                      className="w-full rounded-lg glass-input px-3 py-1.5 text-sm focus:border-orange-500" />
                  </div>
                  <button
                    onClick={() => handleCancel(o.id)}
                    disabled={actionLoadingId === o.id}
                    className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                  >
                    {actionLoadingId === o.id ? "..." : "Conferma annullamento"}
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
