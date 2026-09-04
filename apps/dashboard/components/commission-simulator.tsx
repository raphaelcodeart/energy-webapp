"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { BranchContractRead, BranchMemberRead, SimulationStepRead } from "@/lib/types";

const RANKS = ["S1", "S2", "S3", "TL1", "TL2", "TL3", "TL4", "MD1", "MD2", "MD3", "MD4", "MD5"];

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

async function fetchBranchContracts(agentId: string): Promise<BranchContractRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch-contracts`);
  if (!res.ok) throw new Error("Impossibile caricare i contratti della tua rete.");
  return res.json();
}

async function fetchBranch(agentId: string): Promise<BranchMemberRead[]> {
  const res = await fetch(`/api/proxy/network/agents/${agentId}/branch`);
  if (!res.ok) throw new Error("Impossibile caricare la tua rete.");
  return res.json();
}

export function CommissionSimulator({ agentId }: { agentId: string }) {
  const { data: branchContracts } = useQuery({
    queryKey: ["promoter", "simulator", "branch-contracts", agentId],
    queryFn: () => fetchBranchContracts(agentId),
  });
  const { data: branch } = useQuery({
    queryKey: ["promoter", "simulator", "branch", agentId],
    queryFn: () => fetchBranch(agentId),
  });

  const nameByAgentId = useMemo(() => {
    const map = new Map<string, string>();
    (branch ?? []).forEach((m) => map.set(m.agent_id, `${m.display_name} (${m.promoter_code})`));
    return map;
  }, [branch]);

  const [contractId, setContractId] = useState("");
  const [customContractId, setCustomContractId] = useState("");
  const [useCustom, setUseCustom] = useState(false);

  // Rank override state: key = agent_id, value = rank_code
  const [overrideAgentId, setOverrideAgentId] = useState("");
  const [overrideRank, setOverrideRank] = useState("MD5");
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SimulationStepRead[] | null>(null);

  const addOverride = () => {
    if (!overrideAgentId) return;
    setOverrides((prev) => ({ ...prev, [overrideAgentId]: overrideRank }));
    setOverrideAgentId("");
  };

  const removeOverride = (agentId: string) => {
    setOverrides((prev) => {
      const copy = { ...prev };
      delete copy[agentId];
      return copy;
    });
  };

  const runSimulation = async () => {
    setError(null);
    setResults(null);
    setLoading(true);

    const targetId = useCustom ? customContractId.trim() : contractId;
    if (!targetId) {
      setError(useCustom ? "Inserisci un ID contratto." : "Seleziona un contratto dalla tua rete.");
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`/api/proxy/commissions/contracts/${targetId}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rank_overrides: Object.keys(overrides).length > 0 ? overrides : null,
        }),
      });

      if (!res.ok) {
        throw new Error(await friendlyApiError(res, "Errore durante la simulazione."));
      }

      const data = (await res.json()) as SimulationStepRead[];
      setResults(data);
    } catch (err: any) {
      setError(err.message || "Impossibile caricare i dati della simulazione.");
    } finally {
      setLoading(false);
    }
  };

  const MOVEMENT_LABELS: Record<string, string> = {
    PERSONAL_TOKEN: "Gettone personale",
    ENTREPRENEURIAL_DIFFERENCE: "Differenza imprenditoriale",
    PERSONAL_BONUS: "Bonus personale",
    REVERSAL: "Storno",
  };

  return (
    <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-amber-500/10 rounded-xl border border-amber-500/20 text-amber-400">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white light:text-slate-900">Simulatore Provvigioni</h3>
          <p className="text-xs text-slate-400 light:text-slate-500">
            Scegli un contratto della tua rete e scopri come si dividerebbe la provvigione tra te e la tua filiera.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* Left column: Configuration */}
        <div className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase tracking-wider block mb-2">
              1. Scegli un contratto
            </label>
            <div className="flex flex-col gap-3">
              {!useCustom ? (
                <select
                  value={contractId}
                  onChange={(e) => setContractId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  <option value="">— Seleziona un contratto della tua rete —</option>
                  {(branchContracts ?? []).map((c) => (
                    <option key={c.contract_id} value={c.contract_id} className="bg-slate-950 light:bg-white">
                      {c.customer_name} · {c.product_name} ({STATUS_LABELS[c.status] ?? c.status}) · venduto da {c.producer_name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  placeholder="Incolla l'ID del contratto"
                  value={customContractId}
                  onChange={(e) => setCustomContractId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
                />
              )}
              <button
                type="button"
                onClick={() => setUseCustom((v) => !v)}
                className="self-start text-[11px] text-orange-400 hover:text-orange-300 transition cursor-pointer"
              >
                {useCustom ? "← Torna alla lista dei tuoi contratti" : "Ho già l'ID di un altro contratto →"}
              </button>
            </div>
          </div>

          {/* Rank Overrides Section */}
          <div className="border-t border-white/5 light:border-slate-200 pt-4">
            <h4 className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase tracking-wider mb-2">
              2. Ipotesi (opzionale): cosa succederebbe se...
            </h4>
            <p className="text-[11px] text-slate-400 light:text-slate-500 mb-3">
              Es: &quot;e se Mario fosse già Team Leader invece di Seller quando questo contratto si attiva?&quot;. Scegli
              una persona della tua rete e la qualifica ipotetica, poi premi Aggiungi. Puoi aggiungerne più di una. Se non
              aggiungi nulla, la simulazione usa la qualifica reale e attuale di ciascuno.
            </p>

            <div className="flex flex-col sm:flex-row gap-2 mb-3">
              <select
                value={overrideAgentId}
                onChange={(e) => setOverrideAgentId(e.target.value)}
                className="flex-1 rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
              >
                <option value="">— Scegli una persona della tua rete —</option>
                {(branch ?? [])
                  .filter((m) => m.depth > 0)
                  .map((m) => (
                    <option key={m.agent_id} value={m.agent_id} className="bg-slate-950 light:bg-white">
                      {m.display_name} ({m.promoter_code}) — oggi {m.rank_code ?? "—"}
                    </option>
                  ))}
              </select>
              <div className="flex gap-2">
                <select
                  value={overrideRank}
                  onChange={(e) => setOverrideRank(e.target.value)}
                  className="w-24 rounded-xl glass-input px-2 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  {RANKS.map((r) => (
                    <option key={r} value={r} className="bg-slate-950 light:bg-white">{r}</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={addOverride}
                  disabled={!overrideAgentId}
                  className="px-3 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                >
                  Aggiungi
                </button>
              </div>
            </div>

            {/* List of current overrides */}
            {Object.keys(overrides).length > 0 && (
              <div className="flex flex-wrap gap-2 p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 max-h-32 overflow-y-auto">
                {Object.entries(overrides).map(([agent, rank]) => (
                  <span
                    key={agent}
                    className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800 light:bg-slate-100 border border-slate-700 light:border-slate-300 text-xs text-slate-200 light:text-slate-700"
                  >
                    <span className="text-slate-300 light:text-slate-600">{nameByAgentId.get(agent) ?? agent}</span>
                    <span className="text-slate-500">→</span>
                    <span className="font-bold text-orange-400">{rank}</span>
                    <button
                      type="button"
                      onClick={() => removeOverride(agent)}
                      className="text-rose-400 hover:text-rose-300 font-bold ml-1 cursor-pointer"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={runSimulation}
            disabled={loading}
            className="w-full mt-4 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-400 hover:to-orange-500 py-3 text-sm font-semibold text-white shadow-lg hover:shadow-orange-600/20 transition-all duration-300 disabled:opacity-50 cursor-pointer"
          >
            {loading ? "Calcolo provvigioni in corso..." : "Esegui Simulazione"}
          </button>
        </div>

        {/* Right column: Results */}
        <div className="rounded-xl bg-slate-950/60 light:bg-white/60 border border-white/5 light:border-slate-200 p-4 flex flex-col justify-between min-h-[300px]">
          {loading && (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-400 light:text-slate-500">
              <svg className="animate-spin h-8 w-8 text-amber-500 mb-3" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <p className="text-sm">Analisi della catena degli sponsor in corso...</p>
            </div>
          )}

          {!loading && error && (
            <div className="flex-1 flex flex-col items-center justify-center text-rose-400 text-center px-4">
              <svg className="w-10 h-10 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm font-semibold">Errore simulatore</p>
              <p className="text-xs text-slate-400 light:text-slate-500 mt-1">{error}</p>
            </div>
          )}

          {!loading && !error && !results && (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 text-center">
              <svg className="w-12 h-12 text-slate-600 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              <p className="text-sm">Configura la simulazione e clicca su &quot;Esegui&quot;</p>
              <p className="text-[11px] text-slate-600 mt-1">Simula i gettoni e le differenze imprenditoriali generate.</p>
            </div>
          )}

          {!loading && !error && results && (
            <div className="flex-1 space-y-4">
              <h4 className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase tracking-wider">
                Distribuzione Provvigioni Calcolata:
              </h4>

              {results.length === 0 ? (
                <p className="text-xs text-slate-400 light:text-slate-500 italic">Nessuna provvigione maturata da questa transizione contrattuale (es: contratto non attivabile o stornato).</p>
              ) : (
                <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
                  {results.map((step, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 hover:bg-white/10 transition-all"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-slate-300 light:text-slate-600">
                            {nameByAgentId.get(step.beneficiary_agent_id) ?? `Agente ${step.beneficiary_agent_id.substring(0, 6)}...`}
                          </span>
                          <span className="px-1.5 py-0.5 text-[9px] font-bold bg-orange-500/10 text-orange-400 border border-orange-500/20 rounded">
                            {step.rank_code}
                          </span>
                        </div>
                        <span className="text-sm font-semibold text-emerald-400">
                          +{(step.gross_amount_cents / 100).toFixed(2)} EUR
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 light:text-slate-500 mt-1 font-medium">
                        {MOVEMENT_LABELS[step.movement_type] || step.movement_type}
                      </p>
                      <p className="text-[10px] text-slate-500 mt-0.5 italic">
                        {step.explanation}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {results.length > 0 && (
                <div className="border-t border-white/5 light:border-slate-200 pt-3 flex items-center justify-between text-sm">
                  <span className="text-slate-400 light:text-slate-500 font-medium">Totale Simulato:</span>
                  <span className="font-bold text-emerald-400 text-base">
                    {(results.reduce((sum, r) => sum + r.gross_amount_cents, 0) / 100).toFixed(2)} EUR
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
