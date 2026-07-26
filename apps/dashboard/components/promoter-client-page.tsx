"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell, type NavItem } from "@/components/app-shell";
import { BranchTable } from "@/components/branch-table";
import { BranchVisualizer } from "@/components/branch-visualizer";
import { MyCommissions } from "@/components/my-commissions";
import { CommissionSimulator } from "@/components/commission-simulator";
import { RecruitForm } from "@/components/recruit-form";
import type { AgentProfileRead, BranchMemberRead } from "@/lib/types";

interface PromoterClientPageProps {
  me: AgentProfileRead | null;
  branch: BranchMemberRead[];
  email?: string;
}

const NAV_ITEMS: NavItem[] = [
  {
    key: "network",
    label: "Rete Commerciale",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
      </svg>
    ),
  },
  {
    key: "commissions",
    label: "Movimenti Provvigioni",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3v-6m-3 6v-1m6-13H9a2 2 0 00-2 2v14a2 2 0 002 2h6a2 2 0 002-2V6a2 2 0 00-2-2z" />
      </svg>
    ),
  },
  {
    key: "simulator",
    label: "Simulatore Provvigioni",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
  },
];

export function PromoterClientPage({ me, branch, email }: PromoterClientPageProps) {
  const [activeTab, setActiveTab] = useState<"network" | "commissions" | "simulator">("network");
  const router = useRouter();
  const maxDepth = branch.reduce((max, m) => Math.max(max, m.depth), 0);

  return (
    <AppShell
      roleLabel="Area Promoter"
      email={email}
      navItems={NAV_ITEMS}
      activeKey={activeTab}
      onNavigate={(key) => setActiveTab(key as typeof activeTab)}
      headerTitle={`Benvenuto, ${me?.display_name || "Promoter"}`}
      headerSubtitle="Gestisci la tua rete e simula o monitora le provvigioni."
      headerActions={
        me ? (
          <div className="flex items-center gap-4 bg-slate-900/60 light:bg-slate-50 border border-white/5 light:border-slate-200 rounded-2xl px-5 py-3 glass-card">
            <div>
              <p className="text-[10px] font-bold text-slate-400 light:text-slate-500 uppercase tracking-wider">Codice Promoter</p>
              <p className="font-mono text-base text-amber-400 font-semibold">{me.promoter_code}</p>
            </div>
            <div className="h-8 w-px bg-white/10 light:bg-slate-200" />
            <div>
              <p className="text-[10px] font-bold text-slate-400 light:text-slate-500 uppercase tracking-wider">Qualifica Attuale</p>
              <p className="text-base text-orange-400 font-semibold">{me.current_rank_id || "Nessuna"}</p>
            </div>
          </div>
        ) : undefined
      }
    >
      {!me ? (
        <div className="glass-card rounded-2xl p-8 border-rose-500/10 text-center max-w-xl mx-auto mt-12">
          <svg className="w-12 h-12 text-rose-400 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <h3 className="text-lg font-semibold text-white light:text-slate-900">Nessun profilo agente</h3>
          <p className="text-sm text-slate-400 light:text-slate-500 mt-2">
            Non è stato trovato alcun profilo promoter collegato a questo account. Contatta l&apos;amministratore del sistema per l&apos;assegnazione.
          </p>
        </div>
      ) : (
        <div>
          {activeTab === "network" && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex items-center gap-3 text-xs">
                  <span className="px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold">
                    {branch.length} agenti nel ramo
                  </span>
                  <span className="px-2.5 py-1 rounded-full bg-orange-500/10 text-orange-400 border border-orange-500/20 font-semibold">
                    Profondità massima: {maxDepth} / 12 livelli
                  </span>
                </div>
                <RecruitForm onRecruited={() => router.refresh()} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                  <BranchVisualizer members={branch} />
                </div>
                <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
                  <h3 className="text-lg font-semibold text-white light:text-slate-900 mb-2">Dettaglio Ramo</h3>
                  <p className="text-xs text-slate-400 light:text-slate-500 mb-6">
                    Elenco tabellare di tutti i collaboratori diretti e indiretti, fino a 12 livelli di profondità.
                  </p>
                  <div className="overflow-x-auto">
                    <BranchTable members={branch} />
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "commissions" && (
            <div className="max-w-4xl mx-auto glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
              <h3 className="text-lg font-semibold text-white light:text-slate-900 mb-2">Estratto Conto Provvigioni</h3>
              <p className="text-xs text-slate-400 light:text-slate-500 mb-6">
                Storico dei gettoni personali e delle differenze imprenditoriali maturate sui contratti attivi.
              </p>
              <MyCommissions />
            </div>
          )}

          {activeTab === "simulator" && (
            <div className="max-w-5xl mx-auto">
              <CommissionSimulator />
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
