"use client";

import { useState } from "react";
import { LogoutButton } from "@/components/logout-button";
import type { ContractRead } from "@/lib/types";

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

// Seeded UUIDs for demo quick-fill
const SEED_VALUES = {
  customer: "e2000000-0000-0000-0000-000000000010", // Roberto Villa id or Laura Ferri id
  supplyPoint: "e3000000-0000-0000-0000-000000000020",
  productVersion: "e4000000-0000-0000-0000-000000000030",
  promoter: "e5000000-0000-0000-0000-000000000040" // a5_producer or similar agent id
};

export function AdminClientPage({ initialContracts, email, organizationId }: AdminClientPageProps) {
  const [contracts, setContracts] = useState<ContractRead[]>(initialContracts);
  const [activeTab, setActiveTab] = useState<"list" | "create">("list");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  // State for transitioning a contract
  const [selectedContract, setSelectedContract] = useState<ContractRead | null>(null);
  const [targetStatus, setTargetStatus] = useState("UNDER_REVIEW");
  const [transitionReason, setTransitionReason] = useState("");
  const [transitionNotes, setTransitionNotes] = useState("");
  const [transitionLoading, setTransitionLoading] = useState(false);
  const [transitionError, setTransitionError] = useState<string | null>(null);

  // State for creating a contract
  const [createCustomerId, setCreateCustomerId] = useState("");
  const [createSupplyPointId, setCreateSupplyPointId] = useState("");
  const [createProductVersionId, setCreateProductVersionId] = useState("");
  const [createProducerAgentId, setCreateProducerAgentId] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState(false);

  // Calculate status statistics
  const byStatus = contracts.reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1;
    return acc;
  }, {});

  const filteredContracts = contracts.filter((c) => {
    const matchesSearch =
      c.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.customer_id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "ALL" || c.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const handleOpenTransition = (contract: ContractRead) => {
    setSelectedContract(contract);
    setTransitionReason("");
    setTransitionNotes("");
    setTransitionError(null);
    
    // Choose sensible default transition based on current status
    if (contract.status === "DRAFT") setTargetStatus("SUBMITTED");
    else if (contract.status === "SUBMITTED") setTargetStatus("UNDER_REVIEW");
    else if (contract.status === "UNDER_REVIEW") setTargetStatus("APPROVED");
    else if (contract.status === "APPROVED") setTargetStatus("ACTIVE");
    else setTargetStatus("REJECTED");
  };

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

  const handleCreateContract = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    setCreateSuccess(false);

    try {
      const res = await fetch("/api/proxy/contracts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: createCustomerId.trim(),
          supply_point_id: createSupplyPointId.trim(),
          product_version_id: createProductVersionId.trim(),
          producer_agent_id: createProducerAgentId.trim(),
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Errore nella creazione");
      }

      const newContract = await res.json() as ContractRead;
      
      // Update state and clear inputs
      setContracts(prev => [newContract, ...prev]);
      setCreateSuccess(true);
      setCreateCustomerId("");
      setCreateSupplyPointId("");
      setCreateProductVersionId("");
      setCreateProducerAgentId("");
      
      // Switch back to list after short delay
      setTimeout(() => {
        setActiveTab("list");
        setCreateSuccess(false);
      }, 1500);
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il contratto. Verifica la validità degli ID.");
    } finally {
      setCreateLoading(false);
    }
  };

  const getStatusBadgeColor = (status: string) => {
    switch (status.toUpperCase()) {
      case "ACTIVE":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      case "DRAFT":
        return "bg-slate-500/10 text-slate-400 border-slate-500/20";
      case "REJECTED":
      case "CANCELLED":
        return "bg-rose-500/10 text-rose-400 border-rose-500/20";
      default:
        return "bg-amber-500/10 text-amber-400 border-amber-500/20";
    }
  };

  return (
    <div className="min-h-screen pb-12">
      {/* Top Navigation */}
      <header className="sticky top-0 z-40 w-full border-b border-white/5 bg-slate-950/80 backdrop-blur-md">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-gradient-to-tr from-violet-600 to-cyan-500 shadow-md">
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <span className="text-lg font-bold tracking-tight text-white">
                LIAL <span className="text-violet-400">ENERGY</span>
              </span>
            </div>
            <div className="flex items-center gap-4">
              <div className="hidden sm:flex flex-col text-right">
                <span className="text-xs text-slate-400 font-medium">Area Amministratore</span>
                <span className="text-xs text-slate-300 font-mono">{email}</span>
              </div>
              <LogoutButton />
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 mt-8 animate-slide-up">
        {/* Welcome Section */}
        <div className="mb-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">Pannello Amministrativo</h1>
            <p className="text-sm text-slate-400 mt-1">
              Organizzazione: <span className="font-mono text-xs text-cyan-400">{organizationId}</span>
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setActiveTab("list")}
              className={`px-4 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                activeTab === "list"
                  ? "bg-violet-600 border-violet-500 text-white shadow-lg shadow-violet-500/20"
                  : "bg-white/5 border-white/10 text-slate-300 hover:bg-white/10"
              }`}
            >
              Tutti i Contratti
            </button>
            <button
              onClick={() => setActiveTab("create")}
              className={`px-4 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                activeTab === "create"
                  ? "bg-violet-600 border-violet-500 text-white shadow-lg shadow-violet-500/20"
                  : "bg-white/5 border-white/10 text-slate-300 hover:bg-white/10"
              }`}
            >
              + Nuovo Contratto
            </button>
          </div>
        </div>

        {activeTab === "list" && (
          <div className="space-y-6">
            {/* Quick Metrics Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
              <div className="glass-card rounded-2xl p-4 border-white/5 bg-slate-950/20 text-center">
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">Totali</span>
                <span className="text-2xl font-bold text-white">{contracts.length}</span>
              </div>
              {["DRAFT", "SUBMITTED", "UNDER_REVIEW", "ACTIVE"].map((status) => (
                <div key={status} className="glass-card rounded-2xl p-4 border-white/5 bg-slate-950/20 text-center">
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                    {STATUS_LABELS[status] || status}
                  </span>
                  <span className="text-2xl font-bold text-white">{byStatus[status] ?? 0}</span>
                </div>
              ))}
            </div>

            {/* Filters Bar */}
            <div className="flex flex-col sm:flex-row gap-4 items-center justify-between p-4 rounded-2xl bg-slate-900/40 border border-white/5">
              <div className="w-full sm:max-w-xs relative">
                <input
                  type="text"
                  placeholder="Cerca per UUID contratto o cliente..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full rounded-xl glass-input pl-10 pr-4 py-2 text-xs focus:border-violet-500"
                />
                <svg className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>

              <div className="w-full sm:w-auto flex items-center gap-2">
                <span className="text-xs text-slate-400 shrink-0 font-medium">Stato:</span>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="w-full sm:w-44 rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 focus:border-violet-500"
                >
                  <option value="ALL">Tutti</option>
                  {Object.entries(STATUS_LABELS).map(([code, label]) => (
                    <option key={code} value={code}>{label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Contract List Table */}
            <div className="glass-card rounded-2xl border-white/5 bg-slate-950/40 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/5 text-slate-400 font-semibold bg-white/2">
                      <th className="py-3 px-6">ID Contratto</th>
                      <th className="py-3 px-6">ID Cliente</th>
                      <th className="py-3 px-6">Stato</th>
                      <th className="py-3 px-6 text-right">Azioni</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {filteredContracts.map((c) => (
                      <tr key={c.id} className="text-slate-300 hover:bg-white/5 transition-colors">
                        <td className="py-4 px-6 font-mono text-xs text-white">
                          {c.id}
                        </td>
                        <td className="py-4 px-6 font-mono text-xs text-slate-400">
                          {c.customer_id}
                        </td>
                        <td className="py-4 px-6">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border ${getStatusBadgeColor(c.status)}`}>
                            {STATUS_LABELS[c.status] ?? c.status}
                          </span>
                        </td>
                        <td className="py-4 px-6 text-right">
                          <button
                            onClick={() => handleOpenTransition(c)}
                            className="px-3 py-1 rounded-lg bg-violet-600/10 hover:bg-violet-600/20 border border-violet-500/20 text-violet-400 text-xs font-semibold transition cursor-pointer"
                          >
                            Recensisci
                          </button>
                        </td>
                      </tr>
                    ))}
                    {filteredContracts.length === 0 && (
                      <tr>
                        <td colSpan={4} className="text-center py-8 text-slate-500">
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
          <div className="max-w-xl mx-auto glass-card rounded-2xl p-8 border-white/5 bg-slate-950/40">
            <h3 className="text-lg font-semibold text-white mb-2">Crea un Nuovo Contratto</h3>
            <p className="text-xs text-slate-400 mb-6">
              Compila gli UUID delle entità per generare una nuova proposta contrattuale.
            </p>

            {createSuccess && (
              <div className="p-4 mb-6 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-center animate-scale-up">
                Contratto creato con successo! Verrai reindirizzato all'elenco...
              </div>
            )}

            <form onSubmit={handleCreateContract} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 uppercase block" htmlFor="customerId">
                  UUID Cliente
                </label>
                <input
                  id="customerId"
                  type="text"
                  required
                  placeholder="Inserisci UUID Cliente..."
                  value={createCustomerId}
                  onChange={(e) => setCreateCustomerId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 uppercase block" htmlFor="supplyPointId">
                  UUID Punto Fornitura
                </label>
                <input
                  id="supplyPointId"
                  type="text"
                  required
                  placeholder="Inserisci UUID Supply Point..."
                  value={createSupplyPointId}
                  onChange={(e) => setCreateSupplyPointId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 uppercase block" htmlFor="productVersionId">
                  UUID Versione Prodotto
                </label>
                <input
                  id="productVersionId"
                  type="text"
                  required
                  placeholder="Inserisci UUID Product Version..."
                  value={createProductVersionId}
                  onChange={(e) => setCreateProductVersionId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 uppercase block" htmlFor="producerAgentId">
                  UUID Promoter / Agente
                </label>
                <input
                  id="producerAgentId"
                  type="text"
                  required
                  placeholder="Inserisci UUID Agente Produttore..."
                  value={createProducerAgentId}
                  onChange={(e) => setCreateProducerAgentId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500"
                />
              </div>

              {createError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                  {createError}
                </div>
              )}

              <button
                type="submit"
                disabled={createLoading || createSuccess}
                className="w-full rounded-xl bg-gradient-to-r from-violet-600 to-cyan-500 hover:from-violet-500 hover:to-cyan-400 py-3 text-sm font-semibold text-white shadow-lg transition duration-300 disabled:opacity-50 cursor-pointer mt-2"
              >
                {createLoading ? "Creazione in corso..." : "Genera Contratto"}
              </button>
            </form>
          </div>
        )}
      </main>

      {/* Transition Modal / Drawer Overlay */}
      {selectedContract && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 bg-slate-950 animate-scale-up">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white">Recensisci / Transiziona Stato</h3>
              <button
                onClick={() => setSelectedContract(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 hover:text-white transition cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-3 mb-4 rounded-xl bg-white/5 border border-white/5 text-xs text-slate-400 space-y-1">
              <p>ID Contratto: <span className="font-mono text-white text-[10px]">{selectedContract.id}</span></p>
              <p>Stato Attuale: <span className="font-bold text-violet-400">{STATUS_LABELS[selectedContract.status] || selectedContract.status}</span></p>
            </div>

            <form onSubmit={handleExecuteTransition} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 block">Seleziona Stato di Destinazione</label>
                <select
                  value={targetStatus}
                  onChange={(e) => setTargetStatus(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 focus:border-violet-500"
                >
                  {Object.entries(STATUS_LABELS).map(([code, label]) => (
                    <option key={code} value={code} className="bg-slate-950">{label} ({code})</option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 block">Motivazione</label>
                <input
                  type="text"
                  required
                  placeholder="Es: Documenti validati con successo"
                  value={transitionReason}
                  onChange={(e) => setTransitionReason(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 block">Note aggiuntive (opzionale)</label>
                <textarea
                  rows={3}
                  placeholder="Dettagli interni o appunti..."
                  value={transitionNotes}
                  onChange={(e) => setTransitionNotes(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500 resize-none"
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
                  className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-slate-300 border border-white/5 transition cursor-pointer"
                >
                  Annulla
                </button>
                <button
                  type="submit"
                  disabled={transitionLoading}
                  className="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-xs font-semibold text-white transition cursor-pointer"
                >
                  {transitionLoading ? "Salvataggio..." : "Salva Stato"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
