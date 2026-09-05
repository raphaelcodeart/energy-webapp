"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AppShell, type NavItem } from "@/components/app-shell";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { CustomerProductsPanel } from "@/components/customer-products-panel";
import { CustomerPromoterApplicationCard } from "@/components/customer-promoter-application-card";
import { DocumentationFeed } from "@/components/documentation-feed";
import { SectionBanner } from "@/components/section-banner";
import { SupportTicketsPanel } from "@/components/support-tickets-panel";
import { WalletPanel } from "@/components/wallet-panel";
import { InvoiceRedemptionPanel } from "@/components/invoice-redemption-panel";
import { friendlyApiError } from "@/lib/api-error";
import type { ContractRead, ProductCatalogRead } from "@/lib/types";

function IbanEditor({ contractId, initialIban }: { contractId: string; initialIban: string | null }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(initialIban ?? "");
  const [saved, setSaved] = useState(initialIban);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/iban`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ iban: value.replace(/\s/g, "").toUpperCase() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setSaved(value.replace(/\s/g, "").toUpperCase());
      setEditing(false);
    } catch {
      setError("IBAN non valido. Controlla il formato inserito.");
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <div>
        <span className="text-xs text-slate-500">IBAN per Addebito</span>
        <div className="flex items-center gap-2 mt-0.5">
          <p className="text-xs text-slate-300 light:text-slate-600 font-mono">{saved ?? "Non impostato"}</p>
          <button
            onClick={() => { setValue(saved ?? ""); setEditing(true); }}
            className="text-[10px] font-semibold text-orange-400 hover:text-orange-300 cursor-pointer"
          >
            {saved ? "Modifica" : "Aggiungi"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <span className="text-xs text-slate-500">IBAN per Addebito</span>
      <div className="flex items-center gap-2 mt-0.5">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="IT00A0000000000000000000000"
          className="w-full rounded-lg glass-input px-2 py-1 text-xs uppercase focus:border-orange-500"
        />
        <button onClick={handleSave} disabled={saving} className="text-[10px] font-semibold text-emerald-400 hover:text-emerald-300 cursor-pointer disabled:opacity-50">
          {saving ? "..." : "Salva"}
        </button>
        <button onClick={() => setEditing(false)} className="text-[10px] font-semibold text-slate-500 hover:text-slate-400 cursor-pointer">
          Annulla
        </button>
      </div>
      {error && <p className="text-[10px] text-rose-400 mt-1">{error}</p>}
    </div>
  );
}

async function fetchProductsForLookup(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

interface CustomerClientPageProps {
  contracts: ContractRead[];
  email?: string;
}

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

// Steps for the contract tracker
const STEPS = ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "ACTIVE"];

const NAV_ITEMS: NavItem[] = [
  {
    key: "products",
    label: "Shop",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "contracts",
    label: "I miei Contratti",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    key: "support",
    label: "Supporto & Assistenza",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
  {
    key: "promoter-application",
    label: "Lavora con noi",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-8a4 4 0 11-8 0 4 4 0 018 0zm6 3a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
  },
  {
    key: "documentation",
    label: "Documentazione",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    key: "wallet",
    label: "Wallet",
    notificationTypes: ["CASHBACK_RECEIVED", "WALLET_TRANSFER_RECEIVED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
      </svg>
    ),
  },
  {
    key: "cashback",
    label: "Riscatta Cashback",
    notificationTypes: ["INVOICE_REDEMPTION_VERIFIED", "INVOICE_REDEMPTION_REJECTED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 14l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
];

export function CustomerClientPage({ contracts, email }: CustomerClientPageProps) {
  // "products" (lo shop) is the customer's home -- see NAV_ITEMS ordering below.
  const [activeTab, setActiveTab] = useState<"contracts" | "products" | "support" | "promoter-application" | "documentation" | "wallet" | "cashback">("products");
  // Lazy initializer: Date.now() runs once at mount, not on every render --
  // the sanctioned way to capture an impure value for use during render.
  const [nowMs] = useState(() => Date.now());
  const { data: productsForLookup } = useQuery({
    queryKey: ["customer", "products", "lookup"],
    queryFn: fetchProductsForLookup,
  });
  const productNameByVersionId = new Map(
    (productsForLookup ?? [])
      .filter((p) => p.current_version)
      .map((p) => [p.current_version!.id, p.current_version!.name])
  );

  // Determine current step index in the contract pipeline
  const getStepIndex = (status: string) => {
    const idx = STEPS.indexOf(status.toUpperCase());
    if (idx !== -1) return idx;

    // Heuristics for intermediate statuses
    if (status === "DOCUMENTS_PENDING") return 2; // Under review step
    if (status === "PAYMENT_PENDING" || status === "PAID" || status === "ACTIVATION_PENDING") return 3; // Approved step
    return -1;
  };

  const getStatusColor = (status: string) => {
    switch (status.toUpperCase()) {
      case "ACTIVE":
        return "text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
      case "REJECTED":
      case "CANCELLED":
        return "text-rose-400 bg-rose-500/10 border-rose-500/20";
      case "DRAFT":
        return "text-slate-400 light:text-slate-500 bg-slate-500/10 light:bg-slate-200/50 border-slate-500/20 light:border-slate-300";
      default:
        return "text-amber-400 bg-amber-500/10 border-amber-500/20";
    }
  };

  return (
    <AppShell
      roleLabel="Area Cliente"
      email={email}
      navItems={NAV_ITEMS}
      activeKey={activeTab}
      onNavigate={(key) => setActiveTab(key as typeof activeTab)}
      headerTitle="La mia Area Cliente"
      headerSubtitle="Visualizza lo stato dei tuoi contratti di fornitura luce/gas e richiedi assistenza."
    >
      {activeTab === "contracts" && (
        <div className="space-y-6">
          <SectionBanner image="energy" alt="I miei Contratti" />
          {contracts.length === 0 ? (
            <div className="glass-card rounded-2xl p-12 text-center border-white/5 light:border-slate-200">
              <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <h3 className="text-lg font-semibold text-white light:text-slate-900">Nessun contratto attivo</h3>
              <p className="text-sm text-slate-500 mt-2">
                Non abbiamo trovato nessun contratto di fornitura associato a questa utenza.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {contracts.map((c) => {
                const stepIndex = getStepIndex(c.status);
                const isRejected = c.status === "REJECTED";
                const isCancelled = c.status === "CANCELLED";

                return (
                  <div
                    key={c.id}
                    className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 relative overflow-hidden"
                  >
                    {/* Side Glowing Marker */}
                    <div className={`absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b ${
                      isRejected || isCancelled
                        ? "from-rose-500 to-red-600"
                        : c.status === "ACTIVE"
                          ? "from-emerald-400 to-amber-500"
                          : "from-amber-400 to-orange-500"
                    }`} />

                    {/* Header details */}
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
                      <div>
                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Offerta</p>
                        <h4 className="text-base text-white light:text-slate-900 font-semibold">
                          {c.product_name ?? productNameByVersionId.get(c.product_version_id) ?? "Contratto"}
                        </h4>
                        <p className="font-mono text-[10px] text-slate-500 mt-0.5">{c.id}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getStatusColor(c.status)}`}>
                          {STATUS_LABELS[c.status] ?? c.status}
                        </span>
                      </div>
                    </div>

                    {/* Info grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 mb-6 text-sm">
                      <div>
                        <span className="text-xs text-slate-500">Prodotto</span>
                        <p className="text-xs text-slate-300 light:text-slate-600 mt-0.5">
                          {c.product_name ?? productNameByVersionId.get(c.product_version_id) ?? "—"}
                        </p>
                      </div>
                      <div>
                        <span className="text-xs text-slate-500">Punto di Fornitura</span>
                        <p className="text-xs text-slate-300 light:text-slate-600 mt-0.5">
                          {c.supply_point_label ?? "Punto di fornitura"}
                        </p>
                        <p className="font-mono text-[10px] text-slate-500">{c.supply_point_id}</p>
                      </div>
                      <div>
                        <span className="text-xs text-slate-500">Scadenza / Rinnovo</span>
                        {c.expires_at ? (
                          <p className={`text-xs mt-0.5 font-semibold ${
                            new Date(c.expires_at).getTime() - nowMs < 30 * 24 * 60 * 60 * 1000
                              ? "text-amber-400"
                              : "text-slate-300 light:text-slate-600"
                          }`}>
                            {new Date(c.expires_at).toLocaleDateString("it-IT")}
                          </p>
                        ) : (
                          <p className="text-xs text-slate-500 mt-0.5">—</p>
                        )}
                      </div>
                      <IbanEditor contractId={c.id} initialIban={c.iban} />
                    </div>

                    {/* Documents required for this contract -- upload-only for the
                        customer (review controls are staff-only, see admin-client-page.tsx) */}
                    <div className="mb-6">
                      <h5 className="text-xs font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wider mb-3">
                        Documenti Richiesti
                      </h5>
                      <ContractDocumentsPanel contractId={c.id} />
                    </div>

                    {/* Visual Stepper */}
                    {!isRejected && !isCancelled && stepIndex !== -1 && (
                      <div className="mt-4">
                        <h5 className="text-xs font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wider mb-4">Avanzamento Attivazione</h5>
                        <div className="relative">
                          {/* Connector Line */}
                          <div className="absolute top-4 left-4 right-4 h-0.5 bg-slate-800 light:bg-slate-100 -z-10" />
                          <div
                            className="absolute top-4 left-4 h-0.5 bg-gradient-to-r from-orange-500 to-amber-400 -z-10 transition-all duration-500"
                            style={{ width: `${(stepIndex / (STEPS.length - 1)) * 100}%` }}
                          />

                          <div className="flex justify-between items-center text-center">
                            {STEPS.map((step, idx) => {
                              const isCompleted = idx <= stepIndex;
                              const isActive = idx === stepIndex;

                              return (
                                <div key={step} className="flex flex-col items-center">
                                  <div
                                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border transition-all duration-300 ${
                                      isActive
                                        ? "bg-orange-600 border-orange-500 text-white shadow-lg shadow-orange-600/30 scale-110"
                                        : isCompleted
                                          ? "bg-slate-900 light:bg-white border-amber-500 text-amber-400"
                                          : "bg-slate-950 light:bg-white border-slate-800 light:border-slate-200 text-slate-600"
                                    }`}
                                  >
                                    {isCompleted && !isActive ? (
                                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                      </svg>
                                    ) : (
                                      idx + 1
                                    )}
                                  </div>
                                  <span className={`text-[10px] font-semibold mt-2 ${isActive ? "text-orange-400" : isCompleted ? "text-slate-300 light:text-slate-600" : "text-slate-600"}`}>
                                    {STATUS_LABELS[step] ?? step}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    )}

                    {isRejected && (
                      <div className="flex gap-3 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
                        <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div>
                          <span className="font-semibold block">Attivazione Rifiutata</span>
                          <span className="text-xs text-slate-400 light:text-slate-500">Questo contratto non è stato approvato dagli operatori. Contatta il supporto per maggiori dettagli.</span>
                        </div>
                      </div>
                    )}

                    {isCancelled && (
                      <div className="flex gap-3 p-4 rounded-xl bg-slate-800 light:bg-slate-100 border border-slate-700 light:border-slate-300 text-slate-300 light:text-slate-600 text-sm">
                        <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                        </svg>
                        <div>
                          <span className="font-semibold block">Fornitura Cessata</span>
                          <span className="text-xs text-slate-400 light:text-slate-500">La fornitura per questo punto è stata cessata o disattivata su richiesta dell&apos;utente.</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === "products" && (
        <div className="space-y-6">
          <SectionBanner image="products" alt="Shop" />
          <CustomerPromoterApplicationCard hideWhenActive />
          <CustomerProductsPanel />
        </div>
      )}

      {activeTab === "support" && (
        <div className="space-y-6">
          <SectionBanner image="support" alt="Supporto & Assistenza" />
          <SupportTicketsPanel
            title="Supporto & Assistenza"
            subtitle="Apri un ticket per problemi tecnici, fatturazione o domande sul tuo contratto: un operatore ti risponderà qui."
          />
        </div>
      )}

      {activeTab === "promoter-application" && (
        <div className="space-y-6">
          <CustomerPromoterApplicationCard />
        </div>
      )}

      {activeTab === "documentation" && (
        <div className="space-y-6">
          <SectionBanner image="documentation" alt="Documentazione" />
          <DocumentationFeed />
        </div>
      )}

      {activeTab === "wallet" && (
        <div className="space-y-6">
          <SectionBanner image="wallets" alt="Wallet" />
          <WalletPanel />
        </div>
      )}

      {activeTab === "cashback" && (
        <div className="space-y-6">
          <SectionBanner image="wallets" alt="Riscatta Cashback" />
          <InvoiceRedemptionPanel />
        </div>
      )}
    </AppShell>
  );
}
