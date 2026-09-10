"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ImportedProductRead, ProductCatalogRead } from "@/lib/types";
import { ContractActivationWizard } from "@/components/contract-activation-wizard";
import { ImportedProductCheckoutModal } from "@/components/imported-product-checkout-modal";
import { ProductCheckoutModal } from "@/components/product-checkout-modal";
import { ProductDetailModal } from "@/components/product-detail-modal";
import { ProductThumbnail } from "@/components/product-thumbnail";

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

type ProductCategory = "INTERNAL" | "DROPSHIPPING" | "PARTNER";
// Not a real Product.category value -- the Shop's "Acquisti LialEnergy"
// subcategory is backed by a completely separate table/domain
// (imported_products, see its models.py docstring), shown here as one more
// tab so a customer sees no difference, per explicit user request that this
// stay invisible from the outside. Only ever added to the tab bar when
// showImportedTab is passed (see CustomerProductsPanelProps below) -- every
// other caller of this component keeps behaving exactly as before.
type ShopTab = ProductCategory | "IMPORTED";

const CATEGORY_TABS: { key: ProductCategory; label: string }[] = [
  { key: "INTERNAL", label: "Lial Energy" },
  { key: "PARTNER", label: "Prodotti Partner" },
  // "Fai la spesa con Lial" is a UI label only -- the DROPSHIPPING category
  // key is unchanged in the DB/API (see catalog/models.py::Product.category),
  // same "rename the label, not the value" treatment as admin-products-panel.tsx.
  { key: "DROPSHIPPING", label: "Fai la spesa con Lial" },
];

const ALL_CATEGORIES: ProductCategory[] = ["INTERNAL", "PARTNER", "DROPSHIPPING"];

async function fetchImportedProducts(): Promise<ImportedProductRead[]> {
  const res = await fetch("/api/proxy/imported-products/products/active");
  if (!res.ok) throw new Error("Impossibile caricare gli Acquisti LialEnergy.");
  return res.json();
}

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// Wallet credit is LialCash, never plain EUR -- see wallet-panel.tsx's
// identical helper.
function lialCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} LialCash`;
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
  /** Which category tabs this instance shows -- lets the same component back
      both "Contratti Lial Energy" (INTERNAL only) and "Shop" (PARTNER +
      DROPSHIPPING) without duplicating the catalog grid/cards. Defaults to
      all three, matching the original single-Shop-page behavior (used by the
      promoter's "Condividi" view, which still shares every category). */
  visibleCategories?: ProductCategory[];
  /** The logged-in account's own email, used only to pre-fill (never lock)
      the activation wizard's editable Email field. */
  accountEmail?: string;
  /** Opt-in only -- appends the "Acquisti LialEnergy" tab (imported-products
      plugin) to the Shop's tab bar. Every existing caller (INTERNAL-only
      Home catalog, the promoter "Condividi" view) omits this and keeps
      behaving exactly as before. */
  showImportedTab?: boolean;
}

export function CustomerProductsPanel({
  referralCode,
  organizationId,
  visibleCategories = ALL_CATEGORIES,
  accountEmail,
  showImportedTab = false,
}: CustomerProductsPanelProps = {}) {
  const queryClient = useQueryClient();
  const { data: products, isLoading, error } = useQuery({
    queryKey: ["customer", "products"],
    queryFn: fetchProducts,
  });
  const { data: importedProducts } = useQuery({
    queryKey: ["customer", "imported-products"],
    queryFn: fetchImportedProducts,
    enabled: showImportedTab,
  });
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<ShopTab>(visibleCategories[0] ?? "INTERNAL");
  const [checkoutTarget, setCheckoutTarget] = useState<{ versionId: string; name: string } | null>(null);
  const [importedCheckoutTarget, setImportedCheckoutTarget] = useState<{ id: string; name: string } | null>(null);
  const [detailTarget, setDetailTarget] = useState<ProductCatalogRead | null>(null);
  const [activationTarget, setActivationTarget] = useState<ProductCatalogRead | null>(null);

  const visibleTabs: { key: ShopTab; label: string }[] = [
    ...CATEGORY_TABS.filter((tab) => visibleCategories.includes(tab.key)),
    ...(showImportedTab ? [{ key: "IMPORTED" as ShopTab, label: "Acquisti LialEnergy" }] : []),
  ];

  const activeProducts = (products ?? []).filter(
    (p) => p.status === "ACTIVE" && p.current_version && p.current_version.status === "ACTIVE"
  );
  const catalog = activeProducts.filter((p) => p.category === activeCategory);

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

      {visibleTabs.length > 1 && (
      <div className="flex flex-wrap gap-2">
        {visibleTabs.map((tab) => {
          const count = tab.key === "IMPORTED"
            ? (importedProducts ?? []).length
            : activeProducts.filter((p) => p.category === tab.key).length;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveCategory(tab.key)}
              className={`px-4 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                activeCategory === tab.key
                  ? "bg-orange-600 border-orange-600 text-white"
                  : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
              }`}
            >
              {tab.label}
              {count > 0 && <span className="ml-1.5 opacity-70">({count})</span>}
            </button>
          );
        })}
      </div>
      )}

      {activeCategory === "IMPORTED" ? (
        (importedProducts ?? []).length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-12">Nessun prodotto disponibile al momento.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {(importedProducts ?? []).map((ip, i) => {
              const maxCreditCents = Math.round((ip.price_cents * ip.credit_discount_percentage) / 100);
              return (
                <div
                  key={ip.id}
                  style={{ animationDelay: `${Math.min(i, 8) * 60}ms` }}
                  className="group animate-slide-up glass-card rounded-2xl overflow-hidden border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 hover:border-orange-500/40 hover:-translate-y-1.5 hover:shadow-2xl hover:shadow-orange-500/10 transition-all duration-300"
                >
                  <button
                    type="button"
                    onClick={() => setImportedCheckoutTarget({ id: ip.id, name: ip.name })}
                    className="relative block w-full h-48 overflow-hidden cursor-pointer"
                  >
                    <ProductThumbnail
                      imageUrl={ip.image_url}
                      alt={ip.name}
                      className="w-full h-full object-cover transition-transform duration-500 ease-out group-hover:scale-110"
                      iconClassName="w-12 h-12 text-orange-400/40"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-slate-950/70 via-transparent to-transparent" />
                    {ip.credit_discount_percentage > 0 && (
                      <div className="absolute top-3 right-3">
                        <span className="px-2.5 py-1 rounded-full text-[10px] font-extrabold bg-gradient-to-r from-emerald-500 to-emerald-400 text-white shadow-lg shadow-emerald-500/30">
                          -{ip.credit_discount_percentage}% in LialCash
                        </span>
                      </div>
                    )}
                    <div className="absolute inset-0 flex items-center justify-center bg-slate-950/0 group-hover:bg-slate-950/30 transition-colors duration-300">
                      <span className="opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0 transition-all duration-300 px-3 py-1.5 rounded-lg bg-white/90 text-slate-900 text-[11px] font-bold shadow-lg">
                        Vedi dettagli
                      </span>
                    </div>
                  </button>
                  <div className="p-5">
                    <h4
                      onClick={() => setImportedCheckoutTarget({ id: ip.id, name: ip.name })}
                      className="text-base font-semibold text-white light:text-slate-900 mb-1 leading-snug cursor-pointer hover:text-orange-400 transition"
                    >
                      {ip.name}
                    </h4>
                    {ip.description && (
                      <p className="text-xs text-slate-400 light:text-slate-500 mb-4 line-clamp-2">{ip.description}</p>
                    )}
                    <div className="flex items-end justify-between gap-3 pt-4 border-t border-white/5 light:border-slate-200">
                      <div>
                        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Prezzo</p>
                        <span className="text-2xl font-extrabold text-white light:text-slate-900 tabular-nums">{euro(ip.price_cents)}</span>
                      </div>
                      {maxCreditCents > 0 && (
                        <div className="text-right">
                          <p className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wide">LialCash usabili</p>
                          <p className="text-lg font-extrabold text-emerald-400 tabular-nums">{lialCash(maxCreditCents)}</p>
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => setImportedCheckoutTarget({ id: ip.id, name: ip.name })}
                      className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-white text-xs font-bold shadow-lg shadow-orange-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
                      </svg>
                      Vedi dettagli e acquista
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )
      ) : catalog.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-12">
          {activeCategory === "INTERNAL"
            ? "Nessun prodotto disponibile al momento. Contatta il tuo promoter di riferimento per maggiori informazioni."
            : "Nessun prodotto in questa categoria al momento."}
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {catalog.map((p, i) => {
            const v = p.current_version!;
            const typeLabel = p.product_type === "ENERGY_CONTRACT"
              ? (p.energy_type ? ENERGY_LABELS[p.energy_type] ?? p.energy_type : "Energia")
              : PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type;
            const purchasable = !referralCode && p.category !== "INTERNAL";
            const activatable = !referralCode && p.category === "INTERNAL" && p.product_type === "ENERGY_CONTRACT";
            const maxCreditCents = Math.round((v.base_price_cents * v.credit_discount_percentage) / 100);
            return (
              <div
                key={p.id}
                style={{ animationDelay: `${Math.min(i, 8) * 60}ms` }}
                className="group animate-slide-up glass-card rounded-2xl overflow-hidden border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 hover:border-orange-500/40 hover:-translate-y-1.5 hover:shadow-2xl hover:shadow-orange-500/10 transition-all duration-300"
              >
                <button
                  type="button"
                  onClick={() => purchasable && setDetailTarget(p)}
                  disabled={!purchasable}
                  className={`relative block w-full h-48 overflow-hidden ${purchasable ? "cursor-pointer" : "cursor-default"}`}
                >
                  <ProductThumbnail
                    imageUrl={v.image_url}
                    alt={v.name}
                    className="w-full h-full object-cover transition-transform duration-500 ease-out group-hover:scale-110"
                    iconClassName="w-12 h-12 text-orange-400/40"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-950/70 via-transparent to-transparent" />
                  <div className="absolute top-3 left-3 flex flex-wrap gap-1.5">
                    <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-950/70 backdrop-blur-sm text-white border border-white/10 shadow-lg">
                      {typeLabel}
                    </span>
                  </div>
                  {p.category !== "INTERNAL" && v.credit_discount_percentage > 0 && (
                    <div className="absolute top-3 right-3">
                      <span className="px-2.5 py-1 rounded-full text-[10px] font-extrabold bg-gradient-to-r from-emerald-500 to-emerald-400 text-white shadow-lg shadow-emerald-500/30">
                        -{v.credit_discount_percentage}% in LialCash
                      </span>
                    </div>
                  )}
                  {purchasable && (
                    <div className="absolute inset-0 flex items-center justify-center bg-slate-950/0 group-hover:bg-slate-950/30 transition-colors duration-300">
                      <span className="opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0 transition-all duration-300 px-3 py-1.5 rounded-lg bg-white/90 text-slate-900 text-[11px] font-bold shadow-lg">
                        Vedi dettagli
                      </span>
                    </div>
                  )}
                </button>
                <div className="p-5">
                  <h4
                    onClick={() => purchasable && setDetailTarget(p)}
                    className={`text-base font-semibold text-white light:text-slate-900 mb-1 leading-snug ${purchasable ? "cursor-pointer hover:text-orange-400 transition" : ""}`}
                  >
                    {v.name}
                  </h4>
                  {v.description && (
                    <p className="text-xs text-slate-400 light:text-slate-500 mb-4 line-clamp-2">{v.description}</p>
                  )}

                  <div className="flex items-end justify-between gap-3 pt-4 border-t border-white/5 light:border-slate-200">
                    <div>
                      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Prezzo</p>
                      <div className="flex items-baseline gap-1">
                        <span className="text-2xl font-extrabold text-white light:text-slate-900 tabular-nums">{euro(v.base_price_cents)}</span>
                        <span className="text-[11px] text-slate-500">{BILLING_LABELS[v.billing_period] ?? ""}</span>
                      </div>
                      {v.initial_fee_cents > 0 && (
                        <p className="text-[10px] text-slate-500 mt-0.5">
                          + {euro(v.initial_fee_cents)} attivazione
                        </p>
                      )}
                    </div>
                    {p.category !== "INTERNAL" && maxCreditCents > 0 && (
                      <div className="text-right">
                        <p className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wide">LialCash usabili</p>
                        <p className="text-lg font-extrabold text-emerald-400 tabular-nums">{lialCash(maxCreditCents)}</p>
                      </div>
                    )}
                  </div>

                  {referralCode && (
                    <button
                      onClick={() => shareProduct(p.id, v.name)}
                      className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer"
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
                  {purchasable && (
                    <button
                      onClick={() => setDetailTarget(p)}
                      className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-white text-xs font-bold shadow-lg shadow-orange-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 11H4L5 9z" />
                      </svg>
                      Vedi dettagli e acquista
                    </button>
                  )}
                  {activatable && (
                    <button
                      onClick={() => setActivationTarget(p)}
                      className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-white text-xs font-bold shadow-lg shadow-orange-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      Attiva Contratto
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {detailTarget && (
        <ProductDetailModal
          product={detailTarget}
          onClose={() => setDetailTarget(null)}
          onBuy={(versionId, name) => {
            setDetailTarget(null);
            setCheckoutTarget({ versionId, name });
          }}
        />
      )}

      {checkoutTarget && (
        <ProductCheckoutModal
          productVersionId={checkoutTarget.versionId}
          productName={checkoutTarget.name}
          onClose={() => setCheckoutTarget(null)}
        />
      )}

      {importedCheckoutTarget && (
        <ImportedProductCheckoutModal
          importedProductId={importedCheckoutTarget.id}
          productName={importedCheckoutTarget.name}
          onClose={() => setImportedCheckoutTarget(null)}
        />
      )}

      {activationTarget && (
        <ContractActivationWizard
          product={activationTarget}
          accountEmail={accountEmail}
          onClose={() => setActivationTarget(null)}
          onActivated={() => queryClient.invalidateQueries({ queryKey: ["customer", "contracts"] })}
        />
      )}
    </div>
  );
}
