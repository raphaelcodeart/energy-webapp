"use client";

import { useEffect, useState } from "react";
import type { RankRead } from "@/lib/types";

/** Lets a promoter enroll a new direct collaborator under themselves (calls the
 * network.recruit-gated POST /network/agents/recruit -- scoped server-side to
 * the caller's own agent as parent, see apps/api/app/domains/network/router.py). */
export function RecruitForm({ onRecruited }: { onRecruited: () => void }) {
  const [open, setOpen] = useState(false);
  const [ranks, setRanks] = useState<RankRead[]>([]);
  const [displayName, setDisplayName] = useState("");
  const [promoterCode, setPromoterCode] = useState("");
  const [rankId, setRankId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetch("/api/proxy/commissions/ranks")
      .then((r) => r.json())
      .then(setRanks)
      .catch(() => setRanks([]));
  }, [open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/recruit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: displayName,
          promoter_code: promoterCode,
          current_rank_id: rankId || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setSuccess(true);
      setDisplayName("");
      setPromoterCode("");
      setRankId("");
      onRecruited();
      setTimeout(() => {
        setSuccess(false);
        setOpen(false);
      }, 1200);
    } catch (err: any) {
      setError(err.message || "Impossibile registrare il collaboratore.");
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer"
      >
        + Aggiungi Collaboratore
      </button>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white light:text-slate-900">Nuovo Collaboratore Diretto</h3>
          <button onClick={() => setOpen(false)}
            className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <p className="text-xs text-slate-400 light:text-slate-500 mb-4">
          Verrà inserito come tuo diretto (profondità 1 nel tuo ramo).
        </p>

        {success ? (
          <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-center animate-scale-up">
            Collaboratore registrato!
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome e Cognome</label>
              <input required value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice Promoter</label>
              <input required value={promoterCode} onChange={(e) => setPromoterCode(e.target.value)}
                placeholder="Es: S1-MARIO-ROSSI"
                className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Qualifica iniziale</label>
              <select value={rankId} onChange={(e) => setRankId(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                <option value="">— Nessuna —</option>
                {ranks.map((r) => (
                  <option key={r.id} value={r.id}>{r.code} — {r.name}</option>
                ))}
              </select>
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{error}</div>
            )}

            <div className="flex justify-end gap-3 mt-4">
              <button type="button" onClick={() => setOpen(false)}
                className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                Annulla
              </button>
              <button type="submit" disabled={loading}
                className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                {loading ? "Registrazione..." : "Registra"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
