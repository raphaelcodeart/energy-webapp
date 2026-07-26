"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ProductCatalogRead } from "@/lib/types";

const ENERGY_LABELS: Record<string, string> = {
  ELECTRICITY: "Luce",
  GAS: "Gas",
  DUAL_FUEL: "Dual Fuel",
};

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  DIGITAL: "Digitale",
  PHYSICAL: "Fisico",
  SUBSCRIPTION: "Abbonamento",
};

const BILLING_LABELS: Record<string, string> = {
  MONTHLY: "/mese",
  QUARTERLY: "/trimestre",
  ANNUAL: "/anno",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare il catalogo prodotti.");
  return res.json();
}

interface CustomerProductsPanelProps {
  /** When set, each card gets a "Condividi" button that copies a referral link
      pointing directly at that product -- promoter-only use case. */
  referralCode?: string;
  organizationId?: string;
}

export function CustomerProductsPanel({ referralCode, organizationId }: CustomerProductsPanelProps = {}) {
  const { data: products, isLoading, error } = useQuery({
    queryKey: ["customer", "products"],
    queryFn: fetchProducts,
  });
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const catalog = (products ?? []).filter(
    (p) => p.status === "ACTIVE" && p.current_version && p.current_version.status === "ACTIVE"
  );

  function shareProduct(productId: string, productName: string) {
    if (!referralCode || typeof window === "undefined") return;
    const url = new URL(`/r/${referralCode}`, window.location.origin);
    if (organizationId) url.searchParams.set("org", organizationId);
    url.searchParams.set("product", productId);
    url.searchParams.set("product_name", productName);
    navigator.clipboard.writeText(url.toString());
    setCopiedId(productId);
    setTimeout(() => setCopiedId(null), 2000);
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-400 light:text-slate-500 gap-2">
        <svg className="animate-spin h-5 w-5 text-orange-500" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <span>Caricamento catalogo...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
        Impossibile caricare il catalogo prodotti.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Prodotti & Servizi</h3>
        <p className="text-xs text-slate-400 light:text-slate-500">
          {referralCode
            ? "Condividi un'offerta con un cliente: il link lo porta dritto alla registrazione, già associato a te."
            : "Le offerte luce, gas e dual fuel disponibili per il tuo profilo."}
        </p>
      </div>

      {catalog.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-12">
          Nessun prodotto disponibile al momento. Contatta il tuo promoter di riferimento per maggiori informazioni.
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {catalog.map((p) => {
            const v = p.current_version!;
            const typeLabel = p.product_type === "ENERGY_CONTRACT"
              ? (p.energy_type ? ENERGY_LABELS[p.energy_type] ?? p.energy_type : "Energia")
              : PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type;
            return (
              <div
                key={p.id}
                className="glass-card rounded-2xl overflow-hidden border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 hover:border-orange-500/30 transition-all duration-200"
              >
                <div className="h-40 bg-gradient-to-br from-orange-500/10 to-amber-500/10 flex items-center justify-center overflow-hidden">
                  {v.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- external, admin-supplied URLs
                    <img src={v.image_url} alt={v.name} className="w-full h-full object-cover" />
                  ) : (
                    <svg className="w-12 h-12 text-orange-400/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  )}
                </div>
                <div className="p-5">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20">
                    {typeLabel}
                  </span>
                  <h4 className="text-base font-semibold text-white light:text-slate-900 mt-3 mb-1">{v.name}</h4>
                  {v.description && (
                    <p className="text-xs text-slate-400 light:text-slate-500 mb-4 line-clamp-3">{v.description}</p>
                  )}
                  <div className="flex items-baseline gap-1 pt-3 border-t border-white/5 light:border-slate-200">
                    <span className="text-xl font-bold text-orange-400">{euro(v.base_price_cents)}</span>
                    <span className="text-xs text-slate-500">{BILLING_LABELS[v.billing_period] ?? ""}</span>
                    {v.vat_percentage != null && (
                      <span className="text-[10px] text-slate-500">(IVA {v.vat_percentage}% escl.)</span>
                    )}
                  </div>
                  {v.initial_fee_cents > 0 && (
                    <p className="text-[10px] text-slate-500 mt-1">
                      + {euro(v.initial_fee_cents)} contributo di attivazione
                    </p>
                  )}
                  {referralCode && (
                    <button
                      onClick={() => shareProduct(p.id, v.name)}
                      className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer"
                    >
                      {copiedId === p.id ? (
                        <>
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                          </svg>
                          Link copiato!
                        </>
                      ) : (
                        <>
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342a4 4 0 010-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a4 4 0 105.367-5.925 4 4 0 00-5.367 5.925zm0 8.658a4 4 0 105.367 5.925 4 4 0 00-5.367-5.925z" />
                          </svg>
                          Condividi
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
