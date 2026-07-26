"use client";

import { useQuery } from "@tanstack/react-query";
import type { BranchMemberRead } from "@/lib/types";
import { BranchVisualizer } from "@/components/branch-visualizer";
import { PromoterAziendaPanel } from "@/components/promoter-azienda-panel";

async function fetchBranch(agentId: string): Promise<BranchMemberRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch`);
  if (!res.ok) throw new Error("Impossibile caricare la rete di questo promoter.");
  return res.json();
}

/** Admin-only drill-down into a SPECIFIC promoter's own network -- everything
    that promoter would see logging into their own "La mia Azienda"/"Rete
    Commerciale" tabs (same components, same data, same branch-ownership
    ABAC -- admin roles bypass it, see network/router.py::_assert_branch_access),
    minus the rest of the promoter dashboard shell (shop-sharing, commission
    simulator, support tickets) which isn't relevant from an admin's
    perspective looking in from outside. */
export function AdminPromoterNetworkModal({
  agentId,
  displayName,
  onClose,
}: {
  agentId: string;
  displayName: string;
  onClose: () => void;
}) {
  const { data: branch, error: branchError, isLoading: branchLoading } = useQuery({
    queryKey: ["admin", "promoter-network", "branch", agentId],
    queryFn: () => fetchBranch(agentId),
  });

  const self = branch?.find((m) => m.depth === 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-6xl max-h-[92vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <div className="flex items-start justify-between mb-6 gap-3">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-orange-600 to-amber-500 flex items-center justify-center text-white font-bold text-lg shrink-0">
              {displayName.trim().charAt(0).toUpperCase() || "?"}
            </div>
            <div>
              <h3 className="text-lg font-bold text-white light:text-slate-900">Rete di {displayName}</h3>
              <div className="flex items-center gap-2 mt-0.5">
                {self?.promoter_code && (
                  <span className="font-mono text-[10px] text-slate-500">{self.promoter_code}</span>
                )}
                {self?.rank_code && (
                  <span className="px-2 py-0.5 text-[10px] font-bold rounded-md border bg-white/5 light:bg-slate-900/5 text-slate-300 light:text-slate-600 border-white/10 light:border-slate-300">
                    {self.rank_code}
                  </span>
                )}
                <span className="text-[11px] text-slate-500">
                  Vista amministratore -- gli stessi dati che vede questo promoter, senza il resto della sua dashboard
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer shrink-0"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-6">
          <PromoterAziendaPanel agentId={agentId} />

          <div>
            <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-3">Albero della rete</h4>
            {branchLoading ? (
              <p className="text-sm text-slate-500">Caricamento albero...</p>
            ) : branchError ? (
              <p className="text-sm text-rose-400">Impossibile caricare l&apos;albero della rete.</p>
            ) : branch && branch.length > 0 ? (
              <BranchVisualizer members={branch} />
            ) : (
              <p className="text-sm text-slate-500">Nessun membro della rete da visualizzare.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
