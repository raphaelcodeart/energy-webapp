"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ProductRead } from "@/lib/types";

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

async function fetchProducts(): Promise<ProductRead[]> {
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
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-500/20 transition cursor-pointer shrink-0"
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
            <div key={p.id} className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
              <div className="flex items-center justify-between mb-3">
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-cyan-500/10 text-cyan-400 border-cyan-500/20">
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
              <h4 className="font-mono text-xs text-slate-400 light:text-slate-500 mb-1">{p.code}</h4>
              <p className="text-sm text-slate-300 light:text-slate-600">
                Target: {CUSTOMER_TYPE_LABELS[p.customer_type] ?? p.customer_type}
              </p>
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
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-violet-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
                  <input required value={name} onChange={(e) => setName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo Energia</label>
                  <select value={energyType} onChange={(e) => setEnergyType(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-violet-500">
                    {Object.entries(ENERGY_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cliente Target</label>
                  <select value={customerType} onChange={(e) => setCustomerType(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-violet-500">
                    {Object.entries(CUSTOMER_TYPE_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Descrizione</label>
                <textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500 resize-none" />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Prezzo base (EUR)</label>
                  <input required inputMode="decimal" value={basePriceEuro} onChange={(e) => setBasePriceEuro(e.target.value)}
                    placeholder="18.00"
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Fee iniziale (EUR)</label>
                  <input inputMode="decimal" value={initialFeeEuro} onChange={(e) => setInitialFeeEuro(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Fee ricorrente (EUR)</label>
                  <input inputMode="decimal" value={recurringFeeEuro} onChange={(e) => setRecurringFeeEuro(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Periodicità fatturazione</label>
                <select value={billingPeriod} onChange={(e) => setBillingPeriod(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-violet-500">
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
                  className="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
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
