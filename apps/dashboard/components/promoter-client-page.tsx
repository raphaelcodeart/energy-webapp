"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AppShell, type NavItem } from "@/components/app-shell";
import { BranchTable } from "@/components/branch-table";
import { BranchVisualizer } from "@/components/branch-visualizer";
import { MyCommissions } from "@/components/my-commissions";
import { CommissionSimulator } from "@/components/commission-simulator";
import { CustomerProductsPanel } from "@/components/customer-products-panel";
import { PromoterAziendaPanel } from "@/components/promoter-azienda-panel";
import { RecruitForm } from "@/components/recruit-form";
import { SectionBanner } from "@/components/section-banner";
import { SupportTicketsPanel } from "@/components/support-tickets-panel";
import type { AgentProfileRead, BranchMemberRead, PromoterCodeRead, RankRead } from "@/lib/types";

interface PromoterClientPageProps {
  me: AgentProfileRead | null;
  branch: BranchMemberRead[];
  email?: string;
  organizationId?: string;
}

async function fetchMyReferralCode(): Promise<PromoterCodeRead | null> {
  const res = await fetch("/api/proxy/referral/mine");
  if (!res.ok) throw new Error("Impossibile caricare il link referral.");
  return res.json();
}

async function fetchRanks(): Promise<RankRead[]> {
  const res = await fetch("/api/proxy/commissions/ranks");
  if (!res.ok) throw new Error("Impossibile caricare le qualifiche.");
  return res.json();
}

const NAV_ITEMS: NavItem[] = [
  {
    key: "azienda",
    label: "La mia Azienda",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-4" />
      </svg>
    ),
  },
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
    key: "products",
    label: "Prodotti da Condividere",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
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
  {
    key: "support",
    label: "Supporto",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
];

export function PromoterClientPage({ me, branch, email, organizationId }: PromoterClientPageProps) {
  const [activeTab, setActiveTab] = useState<"azienda" | "network" | "products" | "commissions" | "simulator" | "support">("azienda");
  const router = useRouter();
  const maxDepth = branch.reduce((max, m) => Math.max(max, m.depth), 0);

  const { data: referralCode } = useQuery({
    queryKey: ["promoter", "referral-mine"],
    queryFn: fetchMyReferralCode,
    enabled: !!me,
  });
  const { data: ranks } = useQuery({
    queryKey: ["promoter", "ranks"],
    queryFn: fetchRanks,
    enabled: !!me,
  });
  const rankName = ranks?.find((r) => r.code === me?.rank_code)?.name;
  const [linkCopied, setLinkCopied] = useState(false);

  function copyPersonalLink() {
    if (!referralCode || typeof window === "undefined") return;
    const url = new URL(`/r/${referralCode.code}`, window.location.origin);
    if (organizationId) url.searchParams.set("org", organizationId);
    navigator.clipboard.writeText(url.toString());
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  }

  return (
    <AppShell
      roleLabel="Area Promoter"
      email={email}
      navItems={NAV_ITEMS}
      activeKey={activeTab}
      onNavigate={(key) => setActiveTab(key as typeof activeTab)}
      headerTitle={`Benvenuto, ${me?.display_name || "Promoter"}`}
      centerHeaderActions
      headerActions={
        me ? (
          <div className="w-full flex flex-wrap items-center justify-between gap-4 bg-slate-900/60 light:bg-slate-50 border border-white/5 light:border-slate-200 rounded-2xl px-5 py-3 glass-card">
            <div className="flex flex-wrap items-center gap-4">
              <div>
                <p className="text-[10px] font-bold text-slate-400 light:text-slate-500 uppercase tracking-wider">Codice Promoter</p>
                <p className="font-mono text-base text-amber-400 font-semibold">{me.promoter_code}</p>
              </div>
              <div className="h-8 w-px bg-white/10 light:bg-slate-200" />
              <div>
                <p className="text-[10px] font-bold text-slate-400 light:text-slate-500 uppercase tracking-wider">Qualifica Attuale</p>
                <p className="text-2xl text-orange-400 font-bold leading-tight">{me.rank_code || "Nessuna"}</p>
                {rankName && <p className="text-[10px] text-slate-500 mt-0.5">{rankName}</p>}
              </div>
            </div>
            <button
              onClick={copyPersonalLink}
              disabled={!referralCode}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer disabled:opacity-50"
            >
              {linkCopied ? (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                  Link copiato!
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342a4 4 0 010-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a4 4 0 105.367-5.925 4 4 0 00-5.367 5.925zm0 8.658a4 4 0 105.367 5.925 4 4 0 00-5.367-5.925z" />
                  </svg>
                  Condividi il tuo link
                </>
              )}
            </button>
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
          {activeTab === "azienda" && (
            <div className="space-y-6">
              <SectionBanner image="energy" alt="La mia Azienda" />
              <PromoterAziendaPanel agentId={me.id} />
            </div>
          )}

          {activeTab === "network" && (
            <div className="space-y-6">
              <SectionBanner image="network" alt="Rete Commerciale" />
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

          {activeTab === "products" && (
            <div className="space-y-6">
              <SectionBanner image="products" alt="Prodotti da Condividere" />
              <CustomerProductsPanel referralCode={referralCode?.code} organizationId={organizationId} />
            </div>
          )}

          {activeTab === "commissions" && (
            <div className="max-w-4xl mx-auto space-y-6">
              <SectionBanner image="commissions" alt="Movimenti Provvigioni" />
              <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
                <h3 className="text-lg font-semibold text-white light:text-slate-900 mb-2">Estratto Conto Provvigioni</h3>
                <p className="text-xs text-slate-400 light:text-slate-500 mb-6">
                  Storico dei gettoni personali e delle differenze imprenditoriali maturate sui contratti attivi.
                </p>
                <MyCommissions />
              </div>
            </div>
          )}

          {activeTab === "simulator" && (
            <div className="max-w-5xl mx-auto space-y-6">
              <SectionBanner image="commissions" alt="Simulatore Provvigioni" />
              <CommissionSimulator agentId={me.id} />
            </div>
          )}

          {activeTab === "support" && (
            <div className="space-y-6">
              <SectionBanner image="support" alt="Supporto" />
              <SupportTicketsPanel
                title="Supporto"
                subtitle="Hai bisogno di aiuto dall'amministrazione? Apri un ticket: lo vedrai qui appena ricevi risposta."
              />
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
