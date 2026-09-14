"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import { ShareButtons } from "@/components/share-buttons";
import type { FriendReferralSummaryRead } from "@/lib/types";

const STATE_LABELS: Record<string, string> = {
  INVITED: "Iscritto",
  IN_PROGRESS: "Contratto in corso",
  ACTIVE: "Attivo",
};

const STATE_COLORS: Record<string, string> = {
  INVITED: "bg-white/5 light:bg-slate-900/5 text-slate-400 border-white/10 light:border-slate-300",
  IN_PROGRESS: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  ACTIVE: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
};

const CLAIM_STATUS_LABELS: Record<string, string> = {
  REQUESTED: "In attesa di risposta",
  FULFILLED: "Consegnato",
  REJECTED: "Non accolto",
};

async function fetchSummary(): Promise<FriendReferralSummaryRead> {
  const res = await fetch("/api/proxy/friend-referrals/me");
  if (!res.ok) throw new Error("Impossibile caricare i tuoi inviti.");
  return res.json();
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" });
}

/** "Invita un amico": every account's own one-level invite list.
 *
 * Deliberately NOT the commercial network. There are no commissions here and
 * no hierarchy -- it exists so somebody who is not a promoter can still see
 * who they brought in, and so the "un omaggio ogni 5 attivati" count has
 * somewhere to live. Where an invited customer lands in the commercial tree
 * is decided entirely by the backend, by the existing rules, and is not shown
 * or implied anywhere on this screen.
 */
export function FriendReferralsPanel({ organizationId }: { organizationId?: string }) {
  const queryClient = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["friend-referrals", "me"], queryFn: fetchSummary });
  const [claimLoading, setClaimLoading] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);

  const pagination = usePagination(data?.referrals ?? []);

  function personalLink(): string {
    if (typeof window === "undefined" || !data) return "";
    const url = new URL(`/r/${data.code}`, window.location.origin);
    if (organizationId) url.searchParams.set("org", organizationId);
    return url.toString();
  }

  async function handleClaim() {
    setClaimLoading(true);
    setClaimError(null);
    try {
      const res = await fetch("/api/proxy/friend-referrals/me/reward-claims", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["friend-referrals", "me"] });
    } catch (err: any) {
      setClaimError(err.message || "Impossibile inviare la richiesta.");
    } finally {
      setClaimLoading(false);
    }
  }

  if (error) {
    return <p className="text-sm text-rose-400">Impossibile caricare i tuoi inviti.</p>;
  }
  if (!data) {
    return <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 animate-pulse h-40" />;
  }

  const towardsNext = data.active_total % data.reward_every;
  const progress = data.claimable_milestone ? 100 : (towardsNext / data.reward_every) * 100;

  return (
    <div className="space-y-6">
      {/* Link personale */}
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Invita un amico</h3>
        <p className="text-xs text-slate-400 light:text-slate-500 mt-1 mb-4">
          Condividi il tuo link: chi si iscrive da qui compare nella tua lista. <strong>Ogni{" "}
          {data.reward_every} amici</strong> che attivano un contratto Lial Energy puoi richiedere{" "}
          <strong>{data.reward_description}</strong> &mdash; non solo per i primi {data.reward_every}:
          il premio si ripete a {data.reward_every * 2}, {data.reward_every * 3} e cosi via.
        </p>
        <code className="block w-full truncate rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 px-3 py-2.5 text-xs font-mono text-slate-300 light:text-slate-600 mb-3">
          {personalLink() || `…/r/${data.code}`}
        </code>
        {/* One tap straight into the app they actually use. "Copia link" is
            still there for everything else. */}
        <ShareButtons
          url={personalLink()}
          text="Ti invito in Lial Energy, iscriviti con il mio link:"
        />
      </div>

      {/* Avanzamento verso l'omaggio */}
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-4">
          <div>
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
              Amici invitati con contratto attivo
            </p>
            <p className="text-3xl font-bold text-white light:text-slate-900 tabular-nums">
              {data.active_total}
              <span className="text-base font-semibold text-slate-500"> / {data.invited_total} iscritti</span>
            </p>
          </div>
          {data.claimable_milestone ? (
            <button
              onClick={handleClaim}
              disabled={claimLoading}
              className="px-5 py-2.5 rounded-xl text-xs font-bold bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white shadow-lg shadow-emerald-500/20 transition cursor-pointer disabled:opacity-50"
            >
              {claimLoading ? "Invio..." : `Richiedi ${data.reward_description}`}
            </button>
          ) : (
            <p className="text-xs text-slate-400 light:text-slate-500">
              Ne mancano <strong className="text-orange-400">{data.missing_for_next_reward}</strong> per{" "}
              {data.reward_description}
            </p>
          )}
        </div>

        <div className="h-2 rounded-full bg-white/5 light:bg-slate-900/10 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-orange-500 to-amber-400 transition-all"
            style={{ width: `${Math.min(100, progress)}%` }}
          />
        </div>

        {claimError && (
          <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
            {claimError}
          </div>
        )}

        {data.claims.length > 0 && (
          <div className="mt-5 pt-4 border-t border-white/5 light:border-slate-200 space-y-2">
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Le tue richieste</p>
            {data.claims.map((c) => (
              <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="text-slate-300 light:text-slate-600">
                  Omaggio per {c.milestone} amici attivi
                </span>
                <div className="flex items-center gap-2">
                  {c.note && <span className="text-slate-500">{c.note}</span>}
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                      c.status === "FULFILLED"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : c.status === "REJECTED"
                          ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                          : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                    }`}
                  >
                    {CLAIM_STATUS_LABELS[c.status] ?? c.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* La lista */}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="px-5 pt-5 pb-3">
          <h4 className="text-sm font-semibold text-white light:text-slate-900">Gli amici che hai invitato</h4>
        </div>
        {data.referrals.length === 0 ? (
          <p className="text-center py-10 text-slate-500 text-sm">
            Non hai ancora invitato nessuno. Condividi il tuo link qui sopra.
          </p>
        ) : (
          <>
            <div className="divide-y divide-white/5 light:divide-slate-200">
              {pagination.pageItems.map((r) => (
                <div key={r.id} className="px-5 py-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-white light:text-slate-900">{r.display_name}</p>
                    <p className="text-[11px] text-slate-500">Iscritto il {formatDate(r.invited_at)}</p>
                  </div>
                  <span
                    className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${STATE_COLORS[r.state]}`}
                  >
                    {STATE_LABELS[r.state] ?? r.state}
                  </span>
                </div>
              ))}
            </div>
            <div className="px-5 pb-4">
              <Pagination {...pagination} label="amici invitati" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
