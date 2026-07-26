"use client";

import { useState } from "react";
import { LogoutButton } from "@/components/logout-button";
import { BranchTable } from "@/components/branch-table";
import { BranchVisualizer } from "@/components/branch-visualizer";
import { MyCommissions } from "@/components/my-commissions";
import { CommissionSimulator } from "@/components/commission-simulator";
import { QueryProvider } from "@/app/providers";
import type { AgentProfileRead, BranchMemberRead } from "@/lib/types";

interface PromoterClientPageProps {
  me: AgentProfileRead | null;
  branch: BranchMemberRead[];
  email?: string;
}

export function PromoterClientPage({ me, branch, email }: PromoterClientPageProps) {
  const [activeTab, setActiveTab] = useState<"network" | "commissions" | "simulator">("network");

  return (
    <div className="min-h-screen pb-12">
      {/* Top Glassmorphic Navigation Bar */}
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
                <span className="text-xs text-slate-400 font-medium">Area Promoter</span>
                <span className="text-xs text-slate-300 font-mono">{email}</span>
              </div>
              <LogoutButton />
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 mt-8 animate-slide-up">
        {/* Welcome Section */}
        <div className="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Benvenuto, {me?.display_name || "Promoter"}
            </h1>
            <p className="text-sm text-slate-400 mt-1">Gestisci la tua rete e simula o monitora le provvigioni.</p>
          </div>
          {me && (
            <div className="flex items-center gap-4 bg-slate-900/60 border border-white/5 rounded-2xl px-5 py-3 glass-card">
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Codice Promoter</p>
                <p className="font-mono text-base text-cyan-400 font-semibold">{me.promoter_code}</p>
              </div>
              <div className="h-8 w-px bg-white/10" />
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Qualifica Attuale</p>
                <p className="text-base text-violet-400 font-semibold">{me.current_rank_id || "Nessuna"}</p>
              </div>
            </div>
          )}
        </div>

        {!me ? (
          <div className="glass-card rounded-2xl p-8 border-rose-500/10 text-center max-w-xl mx-auto mt-12">
            <svg className="w-12 h-12 text-rose-400 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 className="text-lg font-semibold text-white">Nessun profilo agente</h3>
            <p className="text-sm text-slate-400 mt-2">
              Non è stato trovato alcun profilo promoter collegato a questo account. Contatta l'amministratore del sistema per l'assegnazione.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Tabs Selector */}
            <div className="border-b border-white/5 flex gap-6 text-sm">
              <button
                onClick={() => setActiveTab("network")}
                className={`pb-4 px-1 font-semibold transition border-b-2 cursor-pointer ${
                  activeTab === "network"
                    ? "border-violet-500 text-violet-400"
                    : "border-transparent text-slate-400 hover:text-slate-300"
                }`}
              >
                Rete Commerciale
              </button>
              <button
                onClick={() => setActiveTab("commissions")}
                className={`pb-4 px-1 font-semibold transition border-b-2 cursor-pointer ${
                  activeTab === "commissions"
                    ? "border-violet-500 text-violet-400"
                    : "border-transparent text-slate-400 hover:text-slate-300"
                }`}
              >
                Movimenti Provvigioni
              </button>
              <button
                onClick={() => setActiveTab("simulator")}
                className={`pb-4 px-1 font-semibold transition border-b-2 cursor-pointer ${
                  activeTab === "simulator"
                    ? "border-violet-500 text-violet-400"
                    : "border-transparent text-slate-400 hover:text-slate-300"
                }`}
              >
                Simulatore Provvigioni
              </button>
            </div>

            {/* Tab Contents */}
            <div className="mt-6">
              {activeTab === "network" && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {/* Left: Interactive Tree Map */}
                  <div className="lg:col-span-2">
                    <BranchVisualizer members={branch} />
                  </div>
                  {/* Right: Flat Table List */}
                  <div className="glass-card rounded-2xl p-6 border-white/5 bg-slate-950/40">
                    <h3 className="text-lg font-semibold text-white mb-2">Dettaglio Ramo</h3>
                    <p className="text-xs text-slate-400 mb-6">
                      Elenco tabellare di tutti i collaboratori diretti e indiretti.
                    </p>
                    <div className="overflow-x-auto">
                      <BranchTable members={branch} />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "commissions" && (
                <div className="max-w-4xl mx-auto glass-card rounded-2xl p-6 border-white/5 bg-slate-950/40">
                  <h3 className="text-lg font-semibold text-white mb-2">Estratto Conto Provvigioni</h3>
                  <p className="text-xs text-slate-400 mb-6">
                    Storico dei gettoni personali e delle differenze imprenditoriali maturate sui contratti attivi.
                  </p>
                  <QueryProvider>
                    <MyCommissions />
                  </QueryProvider>
                </div>
              )}

              {activeTab === "simulator" && (
                <div className="max-w-5xl mx-auto">
                  <CommissionSimulator />
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
