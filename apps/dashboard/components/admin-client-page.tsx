"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AppShell, type NavItem } from "@/components/app-shell";
import { AdminOverviewPanel } from "@/components/admin-overview-panel";
import { AdminCustomersPanel } from "@/components/admin-customers-panel";
import { AdminPromotersPanel } from "@/components/admin-promoters-panel";
import { AdminProductsPanel } from "@/components/admin-products-panel";
import { AdminNetworkPanel } from "@/components/admin-network-panel";
import { AdminCreateContractPanel } from "@/components/admin-create-contract-panel";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { AdminTicketsPanel } from "@/components/admin-tickets-panel";
import { SectionBanner } from "@/components/section-banner";
import type { ContractRead, CustomerRead } from "@/lib/types";

async function fetchCustomersForLookup(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

interface AdminClientPageProps {
  initialContracts: ContractRead[];
  email?: string;
  organizationId?: string;
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

// Mirrors apps/api/app/domains/contracts/state_machine.py::ALLOWED_TRANSITIONS
// exactly -- the dropdown below must only ever offer transitions the backend
// will actually accept. Real bug fixed here: it used to list every status
// unconditionally, so picking anything the state machine didn't allow from
// the contract's current status (e.g. DRAFT -> ACTIVE) always 400'd with
// "Cannot transition contract from X to Y" -- confusing since the UI never
// hinted which choices were valid.
const CONTRACT_ALLOWED_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ["SUBMITTED", "REJECTED"],
  SUBMITTED: ["DOCUMENTS_PENDING", "UNDER_REVIEW", "REJECTED"],
  DOCUMENTS_PENDING: ["UNDER_REVIEW", "REJECTED"],
  UNDER_REVIEW: ["APPROVED", "REJECTED", "DOCUMENTS_PENDING"],
  APPROVED: ["PAYMENT_PENDING", "REJECTED"],
  PAYMENT_PENDING: ["PAID", "REJECTED"],
  PAID: ["ACTIVATION_PENDING"],
  ACTIVATION_PENDING: ["ACTIVE"],
  ACTIVE: ["SUSPENDED", "CANCELLED", "EXPIRED", "RENEWED"],
  SUSPENDED: ["ACTIVE", "CANCELLED"],
  REJECTED: [],
  CANCELLED: [],
  EXPIRED: ["RENEWED", "CANCELLED"],
  RENEWED: ["SUSPENDED", "CANCELLED", "EXPIRED", "RENEWED"],
};

const NAV_ITEMS: NavItem[] = [
  {
    key: "overview",
    label: "Panoramica",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 13h4v8H3v-8zm7-9h4v17h-4V4zm7 5h4v12h-4V9z" />
      </svg>
    ),
  },
  {
    key: "list",
    label: "Tutti i Contratti",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
      </svg>
    ),
  },
  {
    key: "create",
    label: "Nuovo Contratto",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
      </svg>
    ),
  },
  {
    key: "customers",
    label: "Anagrafiche Clienti",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    key: "promoters",
    label: "Anagrafiche Promoter",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
      </svg>
    ),
  },
  {
    key: "products",
    label: "Prodotti & Marketplace",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "network",
    label: "Rete Commerciale",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0H5a2 2 0 01-2-2v-4m6 6h10a2 2 0 002-2v-4m0-6h-6m6 0v6m0-6l-8 8" />
      </svg>
    ),
  },
  {
    key: "tickets",
    label: "Ticket di Supporto",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
];

export function AdminClientPage({ initialContracts, email, organizationId }: AdminClientPageProps) {
  const [contracts, setContracts] = useState<ContractRead[]>(initialContracts);
  const { data: customersForLookup } = useQuery({
    queryKey: ["admin", "customers"],
    queryFn: fetchCustomersForLookup,
  });
  const customerNameById = new Map((customersForLookup ?? []).map((c) => [c.id, c.display_name]));
  const [activeTab, setActiveTab] = useState<"overview" | "list" | "create" | "customers" | "promoters" | "products" | "network" | "tickets">("overview");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [yearFilter, setYearFilter] = useState<string>("ALL");
  // Lazy initializer: Date.now() runs once at mount, not on every render --
  // the sanctioned way to capture an impure value for use during render.
  const [nowMs] = useState(() => Date.now());

  // State for transitioning a contract
  const [selectedContract, setSelectedContract] = useState<ContractRead | null>(null);
  const [targetStatus, setTargetStatus] = useState("UNDER_REVIEW");
  const [transitionReason, setTransitionReason] = useState("");
  const [transitionNotes, setTransitionNotes] = useState("");
  const [transitionLoading, setTransitionLoading] = useState(false);
  const [transitionError, setTransitionError] = useState<string | null>(null);

  // Calculate status statistics
  const byStatus = contracts.reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1;
    return acc;
  }, {});

  const contractYears = Array.from(
    new Set(contracts.map((c) => new Date(c.created_at).getFullYear()))
  ).sort((a, b) => b - a);

  const filteredContracts = contracts.filter((c) => {
    const matchesSearch =
      (c.product_name ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (customerNameById.get(c.customer_id) ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.customer_id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "ALL" || c.status === statusFilter;
    const matchesYear = yearFilter === "ALL" || new Date(c.created_at).getFullYear().toString() === yearFilter;
    return matchesSearch && matchesStatus && matchesYear;
  });

  const EXPIRY_URGENT_MS = 30 * 24 * 60 * 60 * 1000;
  const expiryColor = (expiresAt: string | null) => {
    if (!expiresAt) return "text-slate-500";
    const delta = new Date(expiresAt).getTime() - nowMs;
    if (delta < 0) return "text-rose-400 font-semibold";
    if (delta < EXPIRY_URGENT_MS) return "text-amber-400 font-semibold";
    return "text-slate-300 light:text-slate-600";
  };

  const handleOpenTransition = (contract: ContractRead) => {
    setSelectedContract(contract);
    setTransitionReason("");
    setTransitionNotes("");
    setTransitionError(null);

    // Default to the first status-machine-allowed transition that ISN'T a
    // rejection/cancellation, so the form opens pre-selected on the "happy
    // path" forward step rather than defaulting to REJECTED.
    const allowed = CONTRACT_ALLOWED_TRANSITIONS[contract.status] ?? [];
    const forwardStep = allowed.find((s) => s !== "REJECTED" && s !== "CANCELLED");
    setTargetStatus(forwardStep ?? allowed[0] ?? "");
  };

  const availableTargets = selectedContract ? CONTRACT_ALLOWED_TRANSITIONS[selectedContract.status] ?? [] : [];

  const handleExecuteTransition = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedContract) return;

    setTransitionLoading(true);
    setTransitionError(null);

    try {
      const res = await fetch(`/api/proxy/contracts/${selectedContract.id}/transition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_status: targetStatus,
          reason: transitionReason || null,
          notes: transitionNotes || null,
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Errore transizione");
      }

      const updatedContract = await res.json() as ContractRead;

      // Update local state
      setContracts(prev => prev.map(c => c.id === updatedContract.id ? updatedContract : c));
      setSelectedContract(null);
    } catch (err: any) {
      setTransitionError(err.message || "Transizione fallita. Controlla le regole della macchina di stato.");
    } finally {
      setTransitionLoading(false);
    }
  };

  const handleContractCreated = (newContract: ContractRead) => {
    setContracts((prev) => [newContract, ...prev]);
    setTimeout(() => setActiveTab("list"), 1500);
  };

  const getStatusBadgeColor = (status: string) => {
    switch (status.toUpperCase()) {
      case "ACTIVE":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      case "DRAFT":
        return "bg-slate-500/10 light:bg-slate-200/50 text-slate-400 light:text-slate-500 border-slate-500/20 light:border-slate-300";
      case "REJECTED":
      case "CANCELLED":
        return "bg-rose-500/10 text-rose-400 border-rose-500/20";
      default:
        return "bg-amber-500/10 text-amber-400 border-amber-500/20";
    }
  };

  return (
    <>
      <AppShell
        roleLabel="Area Amministratore"
        email={email}
        navItems={NAV_ITEMS}
        activeKey={activeTab}
        onNavigate={(key) => setActiveTab(key as typeof activeTab)}
        headerTitle="Pannello Amministrativo"
      >
        {activeTab === "overview" && (
          <>
            <SectionBanner image="energy" alt="Panoramica" />
            <AdminOverviewPanel onNavigate={(key) => setActiveTab(key as typeof activeTab)} />
          </>
        )}

        {activeTab === "list" && (
          <div className="space-y-6">
            <SectionBanner image="energy" alt="Contratti" />
            {/* Quick Metrics Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
              <div className="glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/20 light:bg-slate-50 text-center">
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">Totali</span>
                <span className="text-2xl font-bold text-white light:text-slate-900">{contracts.length}</span>
              </div>
              {["DRAFT", "SUBMITTED", "UNDER_REVIEW", "ACTIVE"].map((status) => (
                <div key={status} className="glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/20 light:bg-slate-50 text-center">
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                    {STATUS_LABELS[status] || status}
                  </span>
                  <span className="text-2xl font-bold text-white light:text-slate-900">{byStatus[status] ?? 0}</span>
                </div>
              ))}
            </div>

            {/* Filters Bar */}
            <div className="flex flex-col sm:flex-row gap-4 items-center justify-between p-4 rounded-2xl bg-slate-900/40 light:bg-slate-50 border border-white/5 light:border-slate-200">
              <div className="w-full sm:max-w-xs relative">
                <input
                  type="text"
                  placeholder="Cerca per UUID contratto o cliente..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full rounded-xl glass-input pl-10 pr-4 py-2 text-xs focus:border-orange-500"
                />
                <svg className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>

              <div className="w-full sm:w-auto flex items-center gap-2">
                <span className="text-xs text-slate-400 light:text-slate-500 shrink-0 font-medium">Stato:</span>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="w-full sm:w-44 rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  <option value="ALL">Tutti</option>
                  {Object.entries(STATUS_LABELS).map(([code, label]) => (
                    <option key={code} value={code}>{label}</option>
                  ))}
                </select>
              </div>

              <div className="w-full sm:w-auto flex items-center gap-2">
                <span className="text-xs text-slate-400 light:text-slate-500 shrink-0 font-medium">Anno:</span>
                <select
                  value={yearFilter}
                  onChange={(e) => setYearFilter(e.target.value)}
                  className="w-full sm:w-32 rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  <option value="ALL">Storico completo</option>
                  {contractYears.map((year) => (
                    <option key={year} value={year.toString()}>{year}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Contract List Table */}
            <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold bg-white/2 light:bg-slate-900/[0.02]">
                      <th className="py-3 px-6">Cliente</th>
                      <th className="py-3 px-6">Prodotto / Punto di Fornitura</th>
                      <th className="py-3 px-6">Stato</th>
                      <th className="py-3 px-6">Scadenza / Rinnovo</th>
                      <th className="py-3 px-6 text-right">Azioni</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 light:divide-slate-200">
                    {filteredContracts.map((c) => (
                      <tr key={c.id} className="text-slate-300 light:text-slate-600 hover:bg-white/5 transition-colors">
                        <td className="py-4 px-6">
                          <div className="text-sm font-semibold text-white light:text-slate-900">
                            {customerNameById.get(c.customer_id) ?? "Cliente sconosciuto"}
                          </div>
                          <div className="font-mono text-[10px] text-slate-500">{c.customer_id}</div>
                        </td>
                        <td className="py-4 px-6">
                          <div className="text-xs font-semibold text-white light:text-slate-900">
                            {c.product_name ?? "Prodotto"}
                          </div>
                          <div className="text-[11px] text-slate-400 light:text-slate-500">
                            {c.supply_point_label ?? "Punto di fornitura"}
                          </div>
                          <div className="font-mono text-[10px] text-slate-500">{c.id}</div>
                        </td>
                        <td className="py-4 px-6">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border ${getStatusBadgeColor(c.status)}`}>
                            {STATUS_LABELS[c.status] ?? c.status}
                          </span>
                        </td>
                        <td className="py-4 px-6">
                          <span className={`text-xs ${expiryColor(c.expires_at)}`}>
                            {c.expires_at ? new Date(c.expires_at).toLocaleDateString("it-IT") : "—"}
                          </span>
                        </td>
                        <td className="py-4 px-6 text-right">
                          <button
                            onClick={() => handleOpenTransition(c)}
                            className="px-3 py-1 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer"
                          >
                            Recensisci
                          </button>
                        </td>
                      </tr>
                    ))}
                    {filteredContracts.length === 0 && (
                      <tr>
                        <td colSpan={5} className="text-center py-8 text-slate-500">
                          Nessun contratto corrisponde ai filtri impostati.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === "create" && (
          <div className="space-y-6">
            <SectionBanner image="energy" alt="Nuovo contratto" />
            <AdminCreateContractPanel onCreated={handleContractCreated} />
          </div>
        )}

        {activeTab === "customers" && (
          <div className="space-y-6">
            <SectionBanner image="customers" alt="Clienti" />
            <AdminCustomersPanel />
          </div>
        )}
        {activeTab === "promoters" && (
          <div className="space-y-6">
            <SectionBanner image="network" alt="Promoter" />
            <AdminPromotersPanel />
          </div>
        )}
        {activeTab === "products" && (
          <div className="space-y-6">
            <SectionBanner image="products" alt="Prodotti" />
            <AdminProductsPanel />
          </div>
        )}
        {activeTab === "network" && (
          <div className="space-y-6">
            <SectionBanner image="network" alt="Rete Commerciale" />
            <AdminNetworkPanel />
          </div>
        )}
        {activeTab === "tickets" && (
          <div className="space-y-6">
            <SectionBanner image="support" alt="Ticket di Supporto" />
            <AdminTicketsPanel />
          </div>
        )}
      </AppShell>

      {/* Transition Modal / Drawer Overlay */}
      {selectedContract && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Recensisci / Transiziona Stato</h3>
              <button
                onClick={() => setSelectedContract(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-3 mb-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 text-xs text-slate-400 light:text-slate-500 space-y-1">
              <p>Cliente: <span className="font-semibold text-white light:text-slate-900">{customerNameById.get(selectedContract.customer_id) ?? "Cliente sconosciuto"}</span></p>
              <p>ID Contratto: <span className="font-mono text-white light:text-slate-900 text-[10px]">{selectedContract.id}</span></p>
              <p>Stato Attuale: <span className="font-bold text-orange-400">{STATUS_LABELS[selectedContract.status] || selectedContract.status}</span></p>
            </div>

            <div className="mb-5">
              <p className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase mb-2">Documenti Contrattuali</p>
              <ContractDocumentsPanel contractId={selectedContract.id} isStaff />
            </div>

            {availableTargets.length === 0 ? (
              <div className="p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 text-sm text-slate-400 light:text-slate-500 text-center">
                Questo contratto ha raggiunto uno stato finale ({STATUS_LABELS[selectedContract.status] ?? selectedContract.status}) e non può essere transizionato ulteriormente.
                <div className="flex justify-center mt-4">
                  <button
                    type="button"
                    onClick={() => setSelectedContract(null)}
                    className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer"
                  >
                    Chiudi
                  </button>
                </div>
              </div>
            ) : (
            <form onSubmit={handleExecuteTransition} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 block">Seleziona Stato di Destinazione</label>
                <select
                  value={targetStatus}
                  onChange={(e) => setTargetStatus(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  {availableTargets.map((code) => (
                    <option key={code} value={code} className="bg-slate-950 light:bg-white">{STATUS_LABELS[code] ?? code} ({code})</option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-500 mt-1">
                  Solo le transizioni valide da &quot;{STATUS_LABELS[selectedContract.status] ?? selectedContract.status}&quot; sono elencate qui.
                </p>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 block">Motivazione</label>
                <input
                  type="text"
                  required
                  placeholder="Es: Documenti validati con successo"
                  value={transitionReason}
                  onChange={(e) => setTransitionReason(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 block">Note aggiuntive (opzionale)</label>
                <textarea
                  rows={3}
                  placeholder="Dettagli interni o appunti..."
                  value={transitionNotes}
                  onChange={(e) => setTransitionNotes(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none"
                />
              </div>

              {transitionError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                  {transitionError}
                </div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button
                  type="button"
                  onClick={() => setSelectedContract(null)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer"
                >
                  Annulla
                </button>
                <button
                  type="submit"
                  disabled={transitionLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer"
                >
                  {transitionLoading ? "Salvataggio..." : "Salva Stato"}
                </button>
              </div>
            </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
