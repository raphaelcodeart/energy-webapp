"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pagination, usePagination } from "@/components/pagination";
import { friendlyApiError } from "@/lib/api-error";
import type { FriendReferralAdminClaimRead } from "@/lib/types";

const STATUS_TABS: { key: string; label: string }[] = [
  { key: "REQUESTED", label: "Da gestire" },
  { key: "FULFILLED", label: "Consegnati" },
  { key: "REJECTED", label: "Non accolti" },
  { key: "ALL", label: "Tutti" },
];

const STATUS_COLORS: Record<string, string> = {
  REQUESTED: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  FULFILLED: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  REJECTED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};

const STATUS_LABELS: Record<string, string> = {
  REQUESTED: "Da gestire",
  FULFILLED: "Consegnato",
  REJECTED: "Non accolto",
};

async function fetchClaims(status: string): Promise<FriendReferralAdminClaimRead[]> {
  const res = await fetch(`/api/proxy/friend-referrals/admin/reward-claims?status_filter=${status}`);
  if (!res.ok) throw new Error("Impossibile caricare le richieste omaggio.");
  return res.json();
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** "Omaggi Segnalatori": the requests customers send when they hit a
 *  multiple of 5 activated referrals.
 *
 *  Deliberately NOT an automatic payout -- the business chose to keep a human
 *  in the loop so the gift can be anything (LialCash, a product, a voucher),
 *  decided case by case. The note written here is shown back to the customer.
 */
export function AdminFriendReferralClaimsPanel() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("REQUESTED");
  const [handlingId, setHandlingId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const { data: claims, error } = useQuery({
    queryKey: ["admin", "friend-referral-claims", statusFilter],
    queryFn: () => fetchClaims(statusFilter),
  });

  const pagination = usePagination(claims ?? []);

  async function handle(id: string, status: "FULFILLED" | "REJECTED") {
    setLoadingId(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/friend-referrals/admin/reward-claims/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note: note.trim() || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setHandlingId(null);
      setNote("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "friend-referral-claims"] });
    } catch (err: any) {
      setActionError(err.message || "Impossibile aggiornare la richiesta.");
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Omaggi Segnalatori</h3>
        <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
          Richieste inviate da chi ha raggiunto 5, 10, 15… persone segnalate con un contratto
          <strong> attivo</strong>. L&apos;omaggio non viene accreditato in automatico: decidete voi cosa dare
          e lo segnate qui. La nota che scrivete viene mostrata al cliente.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setStatusFilter(tab.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer border ${
              statusFilter === tab.key
                ? "bg-orange-600 text-white border-orange-500"
                : "bg-white/5 light:bg-slate-900/5 text-slate-300 light:text-slate-600 border-white/10 light:border-slate-300 hover:bg-white/10"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-rose-400">Impossibile caricare le richieste.</p>}
      {actionError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
          {actionError}
        </div>
      )}

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 divide-y divide-white/5 light:divide-slate-200 overflow-hidden">
        {claims === undefined ? (
          <p className="text-center py-8 text-slate-500 text-sm">Caricamento...</p>
        ) : claims.length === 0 ? (
          <p className="text-center py-8 text-slate-500 text-sm">Nessuna richiesta in questo stato.</p>
        ) : (
          pagination.pageItems.map((c) => (
            <div key={c.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-medium text-white light:text-slate-900">{c.referrer_name}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[c.status]}`}>
                      {STATUS_LABELS[c.status] ?? c.status}
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-orange-500/10 text-orange-400 border-orange-500/20">
                      {c.milestone} segnalati attivi
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">
                    {c.referrer_email} · richiesto il {formatDate(c.requested_at)}
                    {c.handled_at ? ` · gestito il ${formatDate(c.handled_at)}` : ""}
                  </p>
                  {c.note && <p className="text-xs text-slate-400 light:text-slate-500 mt-1">Nota: {c.note}</p>}
                </div>
                {c.status === "REQUESTED" && handlingId !== c.id && (
                  <button
                    onClick={() => {
                      setHandlingId(c.id);
                      setNote("");
                      setActionError(null);
                    }}
                    className="shrink-0 px-4 py-2 rounded-xl bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer"
                  >
                    Gestisci
                  </button>
                )}
              </div>

              {handlingId === c.id && (
                <div className="mt-4 pt-4 border-t border-white/5 light:border-slate-200 space-y-3">
                  <div className="space-y-1">
                    <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
                      Nota per il cliente (opzionale)
                    </label>
                    <input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      maxLength={500}
                      placeholder="Es. Buono spesa da 20 euro inviato via email"
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => handle(c.id, "FULFILLED")}
                      disabled={loadingId === c.id}
                      className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                    >
                      {loadingId === c.id ? "..." : "Omaggio consegnato"}
                    </button>
                    <button
                      onClick={() => handle(c.id, "REJECTED")}
                      disabled={loadingId === c.id}
                      className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
                    >
                      {loadingId === c.id ? "..." : "Non accolgo"}
                    </button>
                    <button
                      onClick={() => setHandlingId(null)}
                      className="px-4 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
                    >
                      Annulla
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
      <Pagination {...pagination} label="richieste" />
    </div>
  );
}
