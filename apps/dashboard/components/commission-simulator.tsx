"use client";

import { useState } from "react";
import type { SimulationStepRead } from "@/lib/types";

// Pre-seeded demo contract IDs from data.py for ease of testing
const DEMO_CONTRACTS = [
  { id: "e1000000-0000-0000-0000-000000000001", label: "Roberto Villa - Luce Semplice (Attivo, Produttore a5)" },
  { id: "e2000000-0000-0000-0000-000000000002", label: "Laura Ferri - Gas Semplice (Attivo, Produttore b3)" },
  { id: "e3000000-0000-0000-0000-000000000003", label: "Officine Bianchi - Energia Circolare (Bozza)" },
];

export function CommissionSimulator() {
  const [contractId, setContractId] = useState(DEMO_CONTRACTS[0]?.id || "");
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
    if (!overrideAgentId.trim()) return;
    setOverrides(prev => ({
      ...prev,
      [overrideAgentId.trim()]: overrideRank
    }));
    setOverrideAgentId("");
  };

  const removeOverride = (agentId: string) => {
    setOverrides(prev => {
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
      setError("Inserisci un UUID contratto valido.");
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`/api/proxy/commissions/contracts/${targetId}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rank_overrides: Object.keys(overrides).length > 0 ? overrides : null
        })
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Errore durante la simulazione");
      }

      const data = await res.json() as SimulationStepRead[];
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
    <div className="glass-card rounded-2xl p-6 border-white/5 bg-slate-950/40">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-amber-500/10 rounded-xl border border-amber-500/20 text-amber-400">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">Simulatore Provvigioni</h3>
          <p className="text-xs text-slate-400">Calcola la distribuzione del piano provvigionale in tempo reale</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* Left column: Configuration */}
        <div className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-2">
              Seleziona Contratto
            </label>
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    type="radio"
                    checked={!useCustom}
                    onChange={() => setUseCustom(false)}
                    className="accent-violet-500 cursor-pointer"
                  />
                  Predefiniti Demo
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    type="radio"
                    checked={useCustom}
                    onChange={() => setUseCustom(true)}
                    className="accent-violet-500 cursor-pointer"
                  />
                  ID Personalizzato
                </label>
              </div>

              {!useCustom ? (
                <select
                  value={contractId}
                  onChange={(e) => setContractId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 focus:border-violet-500"
                >
                  {DEMO_CONTRACTS.map(c => (
                    <option key={c.id} value={c.id} className="bg-slate-950">
                      {c.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  placeholder="Inserisci UUID contratto (es: e1000000-...)"
                  value={customContractId}
                  onChange={(e) => setCustomContractId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-violet-500"
                />
              )}
            </div>
          </div>

          {/* Rank Overrides Section */}
          <div className="border-t border-white/5 pt-4">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Sovrascrittura Qualifiche (Overrides)
            </h4>
            <p className="text-[11px] text-slate-400 mb-3">
              Simula cosa succederebbe se un determinato agente avesse una qualifica diversa al momento dell'attivazione.
            </p>

            <div className="flex gap-2 mb-3">
              <input
                type="text"
                placeholder="UUID Agente (es: a0, a1...)"
                value={overrideAgentId}
                onChange={(e) => setOverrideAgentId(e.target.value)}
                className="flex-1 rounded-xl glass-input px-3 py-2 text-xs focus:border-violet-500"
              />
              <select
                value={overrideRank}
                onChange={(e) => setOverrideRank(e.target.value)}
                className="w-24 rounded-xl glass-input px-2 py-2 text-xs bg-slate-900 focus:border-violet-500"
              >
                {["S1", "S2", "S3", "TL1", "TL2", "TL3", "TL4", "MD1", "MD2", "MD3", "MD4", "MD5"].map(r => (
                  <option key={r} value={r} className="bg-slate-950">{r}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={addOverride}
                className="px-3 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-xs font-semibold text-white transition cursor-pointer"
              >
                Aggiungi
              </button>
            </div>

            {/* List of current overrides */}
            {Object.keys(overrides).length > 0 && (
              <div className="flex flex-wrap gap-2 p-3 rounded-xl bg-white/5 border border-white/5 max-h-32 overflow-y-auto">
                {Object.entries(overrides).map(([agent, rank]) => (
                  <span
                    key={agent}
                    className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200"
                  >
                    <span className="font-mono text-[10px] text-slate-400">{agent.substring(0, 6)}...</span>:
                    <span className="font-bold text-violet-400">{rank}</span>
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
            className="w-full mt-4 rounded-xl bg-gradient-to-r from-amber-500 to-violet-600 hover:from-amber-400 hover:to-violet-500 py-3 text-sm font-semibold text-white shadow-lg hover:shadow-violet-600/20 transition-all duration-300 disabled:opacity-50 cursor-pointer"
          >
            {loading ? "Calcolo provvigioni in corso..." : "Esegui Simulazione"}
          </button>
        </div>

        {/* Right column: Results */}
        <div className="rounded-xl bg-slate-950/60 border border-white/5 p-4 flex flex-col justify-between min-h-[300px]">
          {loading && (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
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
              <p className="text-xs text-slate-400 mt-1">{error}</p>
            </div>
          )}

          {!loading && !error && !results && (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 text-center">
              <svg className="w-12 h-12 text-slate-600 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              <p className="text-sm">Configura la simulazione e clicca su "Esegui"</p>
              <p className="text-[11px] text-slate-600 mt-1">Simula i gettoni e le differenze imprenditoriali generate.</p>
            </div>
          )}

          {!loading && !error && results && (
            <div className="flex-1 space-y-4">
              <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                Distribuzione Provvigioni Calcolata:
              </h4>

              {results.length === 0 ? (
                <p className="text-xs text-slate-400 italic">Nessuna provvigione maturata da questa transizione contrattuale (es: contratto non attivabile o stornato).</p>
              ) : (
                <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
                  {results.map((step, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 transition-all"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-slate-300">
                            Agente: {step.beneficiary_agent_id.substring(0, 6)}...
                          </span>
                          <span className="px-1.5 py-0.5 text-[9px] font-bold bg-violet-500/10 text-violet-400 border border-violet-500/20 rounded">
                            {step.rank_code}
                          </span>
                        </div>
                        <span className="text-sm font-semibold text-emerald-400">
                          +{(step.gross_amount_cents / 100).toFixed(2)} EUR
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1 font-medium">
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
                <div className="border-t border-white/5 pt-3 flex items-center justify-between text-sm">
                  <span className="text-slate-400 font-medium">Totale Simulato:</span>
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
