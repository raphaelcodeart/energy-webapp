"use client";

import type { ProductCatalogRead } from "@/lib/types";
import { ProductThumbnail } from "@/components/product-thumbnail";

const BILLING_LABELS: Record<string, string> = {
  MONTHLY: "/mese",
  QUARTERLY: "/trimestre",
  ANNUAL: "/anno",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

/** Full product page shown before checkout -- an e-commerce shopping cart
    never sends the buyer straight from a grid card to payment, it shows the
    product page first. Only ever opened for DROPSHIPPING/PARTNER products
    (see customer-products-panel.tsx's `purchasable` guard); INTERNAL (Lial
    Energy contracts) never gets this treatment -- those become a real
    Contract, not an order, see business-rules.md. */
export function ProductDetailModal({
  product,
  onClose,
  onBuy,
}: {
  product: ProductCatalogRead;
  onClose: () => void;
  onBuy: (versionId: string, name: string) => void;
}) {
  const v = product.current_version!;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-2xl glass-card rounded-2xl border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
        <div className="relative h-64 sm:h-72">
          <ProductThumbnail imageUrl={v.image_url} alt={v.name} iconClassName="w-16 h-16 text-orange-400/40" />
          <button
            onClick={onClose}
            className="absolute top-3 right-3 p-1.5 rounded-lg bg-slate-950/60 hover:bg-slate-950/80 text-white transition cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          {product.category !== "INTERNAL" && v.credit_discount_percentage > 0 && (
            <span className="absolute bottom-3 left-3 px-2.5 py-1 rounded-full text-[11px] font-bold border bg-emerald-500/90 text-white border-emerald-400/50 shadow-lg">
              Fino al {v.credit_discount_percentage}% pagabile in crediti
            </span>
          )}
        </div>

        <div className="p-6 space-y-5">
          <div>
            <h2 className="text-xl font-bold text-white light:text-slate-900">{v.name}</h2>
            {v.description && (
              <p className="text-sm text-slate-400 light:text-slate-500 mt-2 whitespace-pre-wrap">{v.description}</p>
            )}
          </div>

          <div className="flex flex-wrap items-end justify-between gap-4 p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
            <div>
              <p className="text-[10px] text-slate-500 uppercase">Prezzo</p>
              <div className="flex items-baseline gap-1.5">
                <span className="text-2xl font-bold text-orange-400">{euro(v.base_price_cents)}</span>
                <span className="text-xs text-slate-500">{BILLING_LABELS[v.billing_period] ?? ""}</span>
              </div>
              {v.vat_percentage != null && (
                <p className="text-[10px] text-slate-500 mt-0.5">IVA {v.vat_percentage}% esclusa</p>
              )}
              {v.initial_fee_cents > 0 && (
                <p className="text-[10px] text-slate-500 mt-0.5">
                  + {euro(v.initial_fee_cents)} contributo di attivazione
                </p>
              )}
            </div>
            <button
              onClick={() => onBuy(v.id, v.name)}
              className="px-6 py-3 rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold shadow-lg shadow-orange-500/20 transition cursor-pointer"
            >
              Acquista ora
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
