"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { ImportedOrderRead, ImportedProductAdminRead, ImportProviderRead } from "@/lib/types";

const ORDER_STATUS_LABELS: Record<string, string> = {
  AWAITING_PAYMENT: "In attesa di pagamento",
  PAID: "Pagato",
  CANCELLED: "Annullato",
};
const ORDER_STATUS_COLORS: Record<string, string> = {
  AWAITING_PAYMENT: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  PAID: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  CANCELLED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

async function fetchOrders(): Promise<ImportedOrderRead[]> {
  const res = await fetch("/api/proxy/imported-products/orders");
  if (!res.ok) throw new Error("Impossibile caricare gli ordini.");
  return res.json();
}

async function fetchProviders(): Promise<ImportProviderRead[]> {
  const res = await fetch("/api/proxy/imported-products/providers");
  if (!res.ok) throw new Error("Impossibile caricare i provider.");
  return res.json();
}

async function fetchProviderTypes(): Promise<string[]> {
  const res = await fetch("/api/proxy/imported-products/provider-types");
  if (!res.ok) throw new Error("Impossibile caricare i tipi di provider.");
  return res.json();
}

async function fetchProducts(): Promise<ImportedProductAdminRead[]> {
  const res = await fetch("/api/proxy/imported-products/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti importati.");
  return res.json();
}

/** Admin config for the Shop's "Acquisti LialEnergy" plugin (Session 34) --
    two independent sections: import providers (the "bottone per inserire
    API KEY" the user asked for -- type/url/key, AliExpress today, more
    later) and the imported-product catalog itself, added by hand for now
    (see imported_products/models.py -- a real provider sync can be wired
    up later without touching this screen's shape). Deliberately its own
    admin page, never mixed into admin-products-panel.tsx's catalog grid,
    same separation as the backend tables. */
export function AdminImportedProductsPanel() {
  const queryClient = useQueryClient();
  const { data: providers, error: providersError } = useQuery({
    queryKey: ["admin", "import-providers"],
    queryFn: fetchProviders,
  });
  const { data: providerTypes } = useQuery({
    queryKey: ["admin", "import-provider-types"],
    queryFn: fetchProviderTypes,
  });
  const { data: products, error: productsError } = useQuery({
    queryKey: ["admin", "imported-products"],
    queryFn: fetchProducts,
  });
  const { data: orders, error: ordersError } = useQuery({
    queryKey: ["admin", "imported-orders"],
    queryFn: fetchOrders,
  });
  const [orderActionId, setOrderActionId] = useState<string | null>(null);
  const [cancellingOrderId, setCancellingOrderId] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState("");

  // Provider form
  const [providerType, setProviderType] = useState("ALIEXPRESS");
  const [providerName, setProviderName] = useState("");
  const [providerUrl, setProviderUrl] = useState("");
  const [providerKey, setProviderKey] = useState("");
  const [providerCreateLoading, setProviderCreateLoading] = useState(false);
  const [providerCreateError, setProviderCreateError] = useState<string | null>(null);
  const [providerToggleId, setProviderToggleId] = useState<string | null>(null);

  // Product form
  const [showProductForm, setShowProductForm] = useState(false);
  const [pProviderId, setPProviderId] = useState("");
  const [pName, setPName] = useState("");
  const [pDescription, setPDescription] = useState("");
  const [pImageUrl, setPImageUrl] = useState("");
  const [pExternalUrl, setPExternalUrl] = useState("");
  const [pPrice, setPPrice] = useState("");
  const [pCreditPct, setPCreditPct] = useState("0");
  const [productCreateLoading, setProductCreateLoading] = useState(false);
  const [productCreateError, setProductCreateError] = useState<string | null>(null);
  const [productToggleId, setProductToggleId] = useState<string | null>(null);

  async function handleCreateProvider(e: React.FormEvent) {
    e.preventDefault();
    if (!providerName.trim()) return;
    setProviderCreateLoading(true);
    setProviderCreateError(null);
    try {
      const res = await fetch("/api/proxy/imported-products/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_type: providerType, name: providerName.trim(),
          base_url: providerUrl.trim() || null, api_key: providerKey.trim() || null, enabled: true,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setProviderName(""); setProviderUrl(""); setProviderKey("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "import-providers"] });
    } catch (err: any) {
      setProviderCreateError(err.message || "Impossibile creare il provider.");
    } finally {
      setProviderCreateLoading(false);
    }
  }

  async function handleToggleProvider(provider: ImportProviderRead) {
    setProviderToggleId(provider.id);
    try {
      const res = await fetch(`/api/proxy/imported-products/providers/${provider.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !provider.enabled }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "import-providers"] });
    } finally {
      setProviderToggleId(null);
    }
  }

  async function handleCreateProduct(e: React.FormEvent) {
    e.preventDefault();
    const priceCents = Math.round((parseFloat(pPrice.replace(",", ".")) || 0) * 100);
    if (!pProviderId || !pName.trim() || priceCents <= 0) return;
    setProductCreateLoading(true);
    setProductCreateError(null);
    try {
      const res = await fetch("/api/proxy/imported-products/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: pProviderId, name: pName.trim(), description: pDescription.trim(),
          image_url: pImageUrl.trim() || null, external_url: pExternalUrl.trim() || null,
          price_cents: priceCents, credit_discount_percentage: Math.max(0, Math.min(100, parseInt(pCreditPct, 10) || 0)),
          status: "ACTIVE",
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setPName(""); setPDescription(""); setPImageUrl(""); setPExternalUrl(""); setPPrice(""); setPCreditPct("0");
      setShowProductForm(false);
      await queryClient.invalidateQueries({ queryKey: ["admin", "imported-products"] });
    } catch (err: any) {
      setProductCreateError(err.message || "Impossibile creare il prodotto.");
    } finally {
      setProductCreateLoading(false);
    }
  }

  async function handleToggleProduct(product: ImportedProductAdminRead) {
    setProductToggleId(product.id);
    try {
      const res = await fetch(`/api/proxy/imported-products/products/${product.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "imported-products"] });
    } finally {
      setProductToggleId(null);
    }
  }

  async function handleConfirmOrderPayment(id: string) {
    setOrderActionId(id);
    try {
      const res = await fetch(`/api/proxy/imported-products/orders/${id}/confirm-payment`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "imported-orders"] });
    } finally {
      setOrderActionId(null);
    }
  }

  async function handleCancelOrder(id: string) {
    if (!cancelReason.trim()) return;
    setOrderActionId(id);
    try {
      const res = await fetch(`/api/proxy/imported-products/orders/${id}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: cancelReason.trim() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setCancellingOrderId(null);
      setCancelReason("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "imported-orders"] });
    } finally {
      setOrderActionId(null);
    }
  }

  const enabledProviders = (providers ?? []).filter((p) => p.enabled);

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Acquisti LialEnergy</h3>
        <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
          Prodotti importati da un provider esterno (AliExpress e, in futuro, altri) -- compaiono nello Shop del cliente
          come una normale sottocategoria &ldquo;Acquisti LialEnergy&rdquo;, senza mai rivelare la fonte esterna. Il cliente può
          pagarli in parte o interamente con i suoi LialCash, ma questi prodotti non generano mai cashback in cambio.
        </p>
      </div>

      {/* Providers */}
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-1">Nuovo provider di dropshipping</h4>
        <p className="text-xs text-slate-500 mb-4">
          La chiave API non viene mai mostrata di nuovo dopo il salvataggio (solo le ultime 4 cifre) -- stesso trattamento delle chiavi Stripe.
        </p>
        <form onSubmit={handleCreateProvider} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <div className="space-y-1">
            <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo di servizio</label>
            <select
              value={providerType}
              onChange={(e) => setProviderType(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
            >
              {(providerTypes ?? ["ALIEXPRESS"]).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
            <input
              required value={providerName} onChange={(e) => setProviderName(e.target.value)}
              placeholder="Es. AliExpress IT" className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">URL API</label>
            <input
              value={providerUrl} onChange={(e) => setProviderUrl(e.target.value)}
              placeholder="https://api...." className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">API KEY</label>
            <input
              type="password" value={providerKey} onChange={(e) => setProviderKey(e.target.value)}
              placeholder="••••••••" className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
          </div>
          <button
            type="submit" disabled={providerCreateLoading}
            className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {providerCreateLoading ? "..." : "Aggiungi provider"}
          </button>
        </form>
        {providerCreateError && (
          <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{providerCreateError}</div>
        )}
      </div>

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="p-5 pb-3">
          <h4 className="text-sm font-semibold text-white light:text-slate-900">Provider configurati</h4>
        </div>
        {providersError && <p className="px-5 pb-3 text-sm text-rose-400">Impossibile caricare i provider.</p>}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 px-5">Nome</th>
                <th className="py-2 px-5">Tipo</th>
                <th className="py-2 px-5">URL API</th>
                <th className="py-2 px-5">API Key</th>
                <th className="py-2 px-5">Stato</th>
                <th className="py-2 px-5 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {providers === undefined ? (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">Caricamento...</td></tr>
              ) : providers.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">Nessun provider ancora.</td></tr>
              ) : (
                providers.map((p) => (
                  <tr key={p.id} className="text-slate-300 light:text-slate-600">
                    <td className="py-2 px-5 font-medium text-white light:text-slate-900">{p.name}</td>
                    <td className="py-2 px-5">{p.provider_type}</td>
                    <td className="py-2 px-5 text-slate-500 max-w-[200px] truncate">{p.base_url ?? "—"}</td>
                    <td className="py-2 px-5 font-mono">
                      {p.api_key_configured ? `•••• ${p.api_key_last4}` : <span className="text-slate-600">non configurata</span>}
                    </td>
                    <td className="py-2 px-5">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        p.enabled
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          : "bg-slate-500/10 text-slate-400 border-slate-500/20"
                      }`}>
                        {p.enabled ? "Attivo" : "Disattivato"}
                      </span>
                    </td>
                    <td className="py-2 px-5 text-right">
                      <button
                        onClick={() => handleToggleProvider(p)}
                        disabled={providerToggleId === p.id}
                        className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                      >
                        {providerToggleId === p.id ? "..." : p.enabled ? "Disattiva" : "Riattiva"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Products */}
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-white light:text-slate-900">Catalogo prodotti importati</h4>
        <button
          onClick={() => setShowProductForm((v) => !v)}
          disabled={enabledProviders.length === 0}
          className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-40"
          title={enabledProviders.length === 0 ? "Configura prima almeno un provider" : undefined}
        >
          {showProductForm ? "Annulla" : "Aggiungi prodotto"}
        </button>
      </div>

      {showProductForm && (
        <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <form onSubmit={handleCreateProduct} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Provider</label>
              <select
                required value={pProviderId} onChange={(e) => setPProviderId(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              >
                <option value="">Seleziona...</option>
                {enabledProviders.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome prodotto</label>
              <input
                required value={pName} onChange={(e) => setPName(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Descrizione</label>
              <textarea
                value={pDescription} onChange={(e) => setPDescription(e.target.value)} rows={2}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">URL immagine</label>
              <input
                value={pImageUrl} onChange={(e) => setPImageUrl(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
                Link originale (solo admin, mai mostrato al cliente)
              </label>
              <input
                value={pExternalUrl} onChange={(e) => setPExternalUrl(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Prezzo di vendita (&euro;)</label>
              <input
                required inputMode="decimal" value={pPrice} onChange={(e) => setPPrice(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
                % massima pagabile in LialCash
              </label>
              <input
                type="number" min={0} max={100} value={pCreditPct} onChange={(e) => setPCreditPct(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              />
            </div>
            <div className="sm:col-span-2">
              <button
                type="submit" disabled={productCreateLoading}
                className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
              >
                {productCreateLoading ? "..." : "Salva prodotto"}
              </button>
            </div>
          </form>
          {productCreateError && (
            <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{productCreateError}</div>
          )}
        </div>
      )}

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        {productsError && <p className="px-5 pt-5 text-sm text-rose-400">Impossibile caricare i prodotti.</p>}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 px-5">Prodotto</th>
                <th className="py-2 px-5">Provider</th>
                <th className="py-2 px-5 text-right">Prezzo</th>
                <th className="py-2 px-5 text-right">% LialCash</th>
                <th className="py-2 px-5">Stato</th>
                <th className="py-2 px-5 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {products === undefined ? (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">Caricamento...</td></tr>
              ) : products.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-6 text-slate-500">Nessun prodotto ancora.</td></tr>
              ) : (
                products.map((p) => (
                  <tr key={p.id} className="text-slate-300 light:text-slate-600">
                    <td className="py-2 px-5 font-medium text-white light:text-slate-900">{p.name}</td>
                    <td className="py-2 px-5 text-slate-500">{p.provider_name}</td>
                    <td className="py-2 px-5 text-right font-semibold text-white light:text-slate-900">{euro(p.price_cents)}</td>
                    <td className="py-2 px-5 text-right text-emerald-400">{p.credit_discount_percentage}%</td>
                    <td className="py-2 px-5">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        p.status === "ACTIVE"
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          : "bg-slate-500/10 text-slate-400 border-slate-500/20"
                      }`}>
                        {p.status === "ACTIVE" ? "Attivo" : "Disattivato"}
                      </span>
                    </td>
                    <td className="py-2 px-5 text-right">
                      <button
                        onClick={() => handleToggleProduct(p)}
                        disabled={productToggleId === p.id}
                        className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                      >
                        {productToggleId === p.id ? "..." : p.status === "ACTIVE" ? "Disattiva" : "Riattiva"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Orders */}
      <h4 className="text-sm font-semibold text-white light:text-slate-900">Ordini Acquisti LialEnergy</h4>
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        {ordersError && <p className="px-5 pt-5 text-sm text-rose-400">Impossibile caricare gli ordini.</p>}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-2 px-5">Cliente</th>
                <th className="py-2 px-5">Prodotto</th>
                <th className="py-2 px-5 text-right">Totale</th>
                <th className="py-2 px-5 text-right">Residuo</th>
                <th className="py-2 px-5">Metodo</th>
                <th className="py-2 px-5">Stato</th>
                <th className="py-2 px-5 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {orders === undefined ? (
                <tr><td colSpan={7} className="text-center py-6 text-slate-500">Caricamento...</td></tr>
              ) : orders.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-6 text-slate-500">Nessun ordine ancora.</td></tr>
              ) : (
                orders.map((o) => {
                  const awaiting = o.status === "AWAITING_PAYMENT";
                  const busy = orderActionId === o.id;
                  return (
                    <tr key={o.id} className="text-slate-300 light:text-slate-600 align-top">
                      <td className="py-2 px-5">{o.customer_display_name}</td>
                      <td className="py-2 px-5">{o.product_name}</td>
                      <td className="py-2 px-5 text-right font-semibold text-white light:text-slate-900">{euro(o.amount_cents)}</td>
                      <td className="py-2 px-5 text-right">{euro(o.residual_amount_cents)}</td>
                      <td className="py-2 px-5">{o.payment_method === "CARD" ? "Carta" : "Bonifico"}</td>
                      <td className="py-2 px-5">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${ORDER_STATUS_COLORS[o.status]}`}>
                          {ORDER_STATUS_LABELS[o.status]}
                        </span>
                      </td>
                      <td className="py-2 px-5 text-right">
                        {awaiting && (
                          <div className="flex flex-col items-end gap-1.5">
                            {o.payment_method === "BANK_TRANSFER" && (
                              <button
                                onClick={() => handleConfirmOrderPayment(o.id)}
                                disabled={busy}
                                className="px-2.5 py-1 rounded-lg bg-emerald-600/15 hover:bg-emerald-600/25 border border-emerald-500/30 text-emerald-400 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                              >
                                {busy ? "..." : "Conferma bonifico"}
                              </button>
                            )}
                            {cancellingOrderId === o.id ? (
                              <div className="flex items-center gap-1.5">
                                <input
                                  value={cancelReason}
                                  onChange={(e) => setCancelReason(e.target.value)}
                                  placeholder="Motivo"
                                  className="w-28 rounded-lg glass-input px-2 py-1 text-[11px] focus:border-orange-500"
                                />
                                <button
                                  onClick={() => handleCancelOrder(o.id)}
                                  disabled={busy || !cancelReason.trim()}
                                  className="px-2 py-1 rounded-lg bg-rose-600/15 hover:bg-rose-600/25 border border-rose-500/30 text-rose-400 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                                >
                                  OK
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setCancellingOrderId(o.id)}
                                className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-[11px] font-semibold transition cursor-pointer"
                              >
                                Annulla ordine
                              </button>
                            )}
                          </div>
                        )}
                      </td>
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
