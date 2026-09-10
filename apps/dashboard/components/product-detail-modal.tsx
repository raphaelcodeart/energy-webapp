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

// Wallet credit is LialCash, never plain EUR -- see wallet-panel.tsx's
// identical helper.
function lialCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} LialCash`;
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
              Fino al {v.credit_discount_percentage}% pagabile in LialCash
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

          <div className="flex flex-wrap items-end gap-6 p-5 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
            <div>
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Prezzo</p>
              <div className="flex items-baseline gap-1.5">
                <span className="text-3xl font-extrabold text-white light:text-slate-900 tabular-nums">{euro(v.base_price_cents)}</span>
                <span className="text-xs text-slate-500">{BILLING_LABELS[v.billing_period] ?? ""}</span>
              </div>
              {v.vat_percentage != null && (
                <p className="text-[10px] text-slate-500 mt-0.5">
                  + IVA {v.vat_percentage}% ({euro(Math.round(v.base_price_cents * (1 + v.vat_percentage / 100)))} tot.)
                </p>
              )}
              {v.initial_fee_cents > 0 && (
                <p className="text-[10px] text-slate-500 mt-0.5">
                  + {euro(v.initial_fee_cents)} contributo di attivazione
                </p>
              )}
            </div>
            {product.category !== "INTERNAL" && v.credit_discount_percentage > 0 && (
              <div className="pl-6 border-l border-white/10 light:border-slate-300">
                <p className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wide">LialCash usabili</p>
                <p className="text-3xl font-extrabold text-emerald-400 tabular-nums">
                  {lialCash(Math.round((v.base_price_cents * v.credit_discount_percentage) / 100))}
                </p>
                <p className="text-[10px] text-slate-500 mt-0.5">dal tuo wallet Lial Energy</p>
              </div>
            )}
          </div>

          <button
            onClick={() => onBuy(v.id, v.name)}
            className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-white text-sm font-bold shadow-lg shadow-orange-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
          >
            <svg className="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
            </svg>
            Acquista ora
          </button>
        </div>
      </div>
    </div>
  );
}
