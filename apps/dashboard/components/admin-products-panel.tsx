"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ProductCatalogRead } from "@/lib/types";

const ENERGY_LABELS: Record<string, string> = {
  ELECTRICITY: "Luce",
  GAS: "Gas",
  DUAL_FUEL: "Dual Fuel",
};

const CUSTOMER_TYPE_LABELS: Record<string, string> = {
  PRIVATE: "Privati",
  SOLE_PROPRIETOR: "Partita IVA",
  PMI: "PMI",
  CONDOMINIUM: "Condominio",
  ENERGY_INTENSIVE: "Energivori",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

export function AdminProductsPanel() {
  const queryClient = useQueryClient();
  const { data: products, error: loadError } = useQuery({
    queryKey: ["admin", "products"],
    queryFn: fetchProducts,
  });
  const [showCreate, setShowCreate] = useState(false);

  const [code, setCode] = useState("");
  const [energyType, setEnergyType] = useState("ELECTRICITY");
  const [customerType, setCustomerType] = useState("PRIVATE");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [basePriceEuro, setBasePriceEuro] = useState("");
  const [initialFeeEuro, setInitialFeeEuro] = useState("0");
  const [recurringFeeEuro, setRecurringFeeEuro] = useState("0");
  const [billingPeriod, setBillingPeriod] = useState("MONTHLY");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  function euroToCents(value: string): number {
    const parsed = parseFloat(value.replace(",", "."));
    return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          energy_type: energyType,
          customer_type: customerType,
          name,
          description,
          image_url: imageUrl.trim() || null,
          base_price_cents: euroToCents(basePriceEuro),
          initial_fee_cents: euroToCents(initialFeeEuro),
          recurring_fee_cents: euroToCents(recurringFeeEuro),
          billing_period: billingPeriod,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setShowCreate(false);
      setCode("");
      setName("");
      setDescription("");
      setImageUrl("");
      setBasePriceEuro("");
      setInitialFeeEuro("0");
      setRecurringFeeEuro("0");
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il prodotto.");
    } finally {
      setCreateLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400 light:text-slate-500">
          Cataloghi luce, gas, dual fuel ed Energia Circolare venduti in marketplace.
        </p>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
        >
          + Nuovo Prodotto
        </button>
      </div>

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare i prodotti.</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {products === undefined ? (
          <p className="text-sm text-slate-500 col-span-full text-center py-8">Caricamento...</p>
        ) : products.length === 0 ? (
          <p className="text-sm text-slate-500 col-span-full text-center py-8">Nessun prodotto nel catalogo.</p>
        ) : (
          products.map((p) => (
            <div key={p.id} className="glass-card rounded-2xl overflow-hidden border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
              <div className="h-32 bg-slate-900 light:bg-slate-100 flex items-center justify-center overflow-hidden">
                {p.current_version?.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element -- external, admin-supplied URLs; not part of the Next asset pipeline
                  <img src={p.current_version.image_url} alt={p.current_version.name} className="w-full h-full object-cover" />
                ) : (
                  <svg className="w-10 h-10 text-slate-700 light:text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14M4 8h16M4 4h16v16H4V4z" />
                  </svg>
                )}
              </div>
              <div className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20">
                    {ENERGY_LABELS[p.energy_type] ?? p.energy_type}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                    p.status === "ACTIVE"
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      : "bg-slate-500/10 light:bg-slate-200/50 text-slate-400 light:text-slate-500 border-slate-500/20 light:border-slate-300"
                  }`}>
                    {p.status}
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-0.5">
                  {p.current_version?.name ?? p.code}
                </h4>
                <p className="font-mono text-[10px] text-slate-500 mb-2">{p.code}</p>
                {p.current_version?.description && (
                  <p className="text-xs text-slate-400 light:text-slate-500 mb-3 line-clamp-2">
                    {p.current_version.description}
                  </p>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400 light:text-slate-500">
                    Target: {CUSTOMER_TYPE_LABELS[p.customer_type] ?? p.customer_type}
                  </span>
                  {p.current_version && (
                    <span className="text-sm font-bold text-orange-400">
                      {euro(p.current_version.base_price_cents)}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Nuovo Prodotto</h3>
              <button onClick={() => setShowCreate(false)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice</label>
                  <input required value={code} onChange={(e) => setCode(e.target.value)} placeholder="Es: LUCE-PMI-01"
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
                  <input required value={name} onChange={(e) => setName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo Energia</label>
                  <select value={energyType} onChange={(e) => setEnergyType(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                    {Object.entries(ENERGY_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cliente Target</label>
                  <select value={customerType} onChange={(e) => setCustomerType(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                    {Object.entries(CUSTOMER_TYPE_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Descrizione</label>
                <textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)}
                  placeholder="Descrizione visibile ai clienti nel marketplace..."
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Foto prodotto (URL immagine)</label>
                <input value={imageUrl} onChange={(e) => setImageUrl(e.target.value)}
                  placeholder="https://..."
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Prezzo base (EUR)</label>
                  <input required inputMode="decimal" value={basePriceEuro} onChange={(e) => setBasePriceEuro(e.target.value)}
                    placeholder="18.00"
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Fee iniziale (EUR)</label>
                  <input inputMode="decimal" value={initialFeeEuro} onChange={(e) => setInitialFeeEuro(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Fee ricorrente (EUR)</label>
                  <input inputMode="decimal" value={recurringFeeEuro} onChange={(e) => setRecurringFeeEuro(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Periodicità fatturazione</label>
                <select value={billingPeriod} onChange={(e) => setBillingPeriod(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                  <option value="MONTHLY">Mensile</option>
                  <option value="QUARTERLY">Trimestrale</option>
                  <option value="ANNUAL">Annuale</option>
                </select>
              </div>

              {createError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={createLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {createLoading ? "Creazione..." : "Crea Prodotto"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
