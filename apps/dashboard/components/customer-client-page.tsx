"use client";

import { useState } from "react";
import { AppShell, type NavItem } from "@/components/app-shell";
import type { ContractRead } from "@/lib/types";

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
];

export function CustomerClientPage({ contracts, email }: CustomerClientPageProps) {
  const [activeTab, setActiveTab] = useState<"contracts" | "support">("contracts");

  // Support ticket state
  const [ticketSubject, setTicketSubject] = useState("");
  const [ticketMessage, setTicketMessage] = useState("");
  const [ticketType, setTicketType] = useState("ASSISTENZA_TECNICA");
  const [ticketSubmitted, setTicketSubmitted] = useState(false);
  const [submittingTicket, setSubmittingTicket] = useState(false);
  const [ticketNumber, setTicketNumber] = useState<number | null>(null);

  const handleSupportSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmittingTicket(true);
    // Generated here (an event handler), not during render, so it stays stable
    // across re-renders instead of changing every time the component re-paints.
    const newTicketNumber = Math.floor(Math.random() * 90000) + 10000;
    setTimeout(() => {
      setSubmittingTicket(false);
      setTicketSubmitted(true);
      setTicketNumber(newTicketNumber);
      setTicketSubject("");
      setTicketMessage("");
      setTimeout(() => setTicketSubmitted(false), 5000);
    }, 1200);
  };

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
                          ? "from-emerald-400 to-cyan-500"
                          : "from-amber-400 to-violet-500"
                    }`} />

                    {/* Header details */}
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
                      <div>
                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Codice Contratto</p>
                        <h4 className="font-mono text-sm text-white light:text-slate-900 font-semibold">{c.id}</h4>
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
                        <span className="text-xs text-slate-500">ID Cliente</span>
                        <p className="font-mono text-xs text-slate-300 light:text-slate-600 mt-0.5">{c.customer_id}</p>
                      </div>
                      <div>
                        <span className="text-xs text-slate-500">Punto di Fornitura (POD/PDR)</span>
                        <p className="font-mono text-xs text-slate-300 light:text-slate-600 mt-0.5">{c.supply_point_id}</p>
                      </div>
                      <div>
                        <span className="text-xs text-slate-500">Codice Prodotto</span>
                        <p className="font-mono text-xs text-slate-300 light:text-slate-600 mt-0.5">{c.product_version_id}</p>
                      </div>
                    </div>

                    {/* Visual Stepper */}
                    {!isRejected && !isCancelled && stepIndex !== -1 && (
                      <div className="mt-4">
                        <h5 className="text-xs font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wider mb-4">Avanzamento Attivazione</h5>
                        <div className="relative">
                          {/* Connector Line */}
                          <div className="absolute top-4 left-4 right-4 h-0.5 bg-slate-800 light:bg-slate-100 -z-10" />
                          <div
                            className="absolute top-4 left-4 h-0.5 bg-gradient-to-r from-violet-500 to-cyan-400 -z-10 transition-all duration-500"
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
                                        ? "bg-violet-600 border-violet-500 text-white shadow-lg shadow-violet-600/30 scale-110"
                                        : isCompleted
                                          ? "bg-slate-900 light:bg-white border-cyan-500 text-cyan-400"
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
                                  <span className={`text-[10px] font-semibold mt-2 ${isActive ? "text-violet-400" : isCompleted ? "text-slate-300 light:text-slate-600" : "text-slate-600"}`}>
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

      {activeTab === "support" && (
        <div className="max-w-2xl mx-auto glass-card rounded-2xl p-8 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-violet-500/10 rounded-xl border border-violet-500/20 text-violet-400">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white light:text-slate-900">Invia Segnalazione / Richiesta</h3>
              <p className="text-xs text-slate-400 light:text-slate-500">Il nostro team di supporto ti ricontatterà entro 24 ore</p>
            </div>
          </div>

          {ticketSubmitted ? (
            <div className="p-6 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-center animate-scale-up space-y-2">
              <svg className="w-10 h-10 mx-auto text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h4 className="font-semibold text-white light:text-slate-900">Richiesta Ricevuta!</h4>
              <p className="text-xs text-slate-300 light:text-slate-600">La segnalazione è stata presa in carico dagli operatori con il ticket #LIAL-{ticketNumber}.</p>
            </div>
          ) : (
            <form onSubmit={handleSupportSubmit} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wider" htmlFor="ticketType">
                    Tipo di richiesta
                  </label>
                  <select
                    id="ticketType"
                    value={ticketType}
                    onChange={(e) => setTicketType(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm bg-slate-900 light:bg-white focus:border-violet-500"
                  >
                    <option value="ASSISTENZA_TECNICA" className="bg-slate-950 light:bg-white">Problema Tecnico</option>
                    <option value="FATTURAZIONE" className="bg-slate-950 light:bg-white">Fatture e Consumi</option>
                    <option value="SUBENTRO_VOLTURA" className="bg-slate-950 light:bg-white">Subentri e Volture</option>
                    <option value="INFORMAZIONI" className="bg-slate-950 light:bg-white">Richiesta Informazioni</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wider" htmlFor="subject">
                    Oggetto
                  </label>
                  <input
                    id="subject"
                    type="text"
                    required
                    placeholder="Breve descrizione..."
                    value={ticketSubject}
                    onChange={(e) => setTicketSubject(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wider" htmlFor="message">
                  Messaggio dettagliato
                  </label>
                <textarea
                  id="message"
                  required
                  rows={5}
                  placeholder="Descrivi qui la tua richiesta o il problema riscontrato..."
                  value={ticketMessage}
                  onChange={(e) => setTicketMessage(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-violet-500 resize-none"
                />
              </div>

              <button
                type="submit"
                disabled={submittingTicket}
                className="w-full rounded-xl bg-gradient-to-r from-violet-600 to-cyan-500 hover:from-violet-500 hover:to-cyan-400 py-3 text-sm font-semibold text-white shadow-lg transition-all duration-300 disabled:opacity-50 cursor-pointer mt-2"
              >
                {submittingTicket ? "Invio in corso..." : "Invia Messaggio"}
              </button>
            </form>
          )}
        </div>
      )}
    </AppShell>
  );
}
