"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { friendlyApiError } from "@/lib/api-error";
import type { AgentProfileRead } from "@/lib/types";

async function fetchMyApplication(): Promise<AgentProfileRead | null> {
  const res = await fetch("/api/proxy/network/agents/me");
  if (!res.ok) throw new Error("Impossibile caricare lo stato della richiesta.");
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

interface CustomerPromoterApplicationCardProps {
  /** When true, renders nothing at all once the caller is an ACTIVE promoter
   * -- used on the customer home page, where the point of the card is only to
   * invite; once accepted, the always-visible area switcher (app-shell.tsx)
   * takes over as the way to reach the promoter dashboard. The dedicated
   * "Lavora con noi" tab keeps hideWhenActive unset, so it still shows a
   * confirmation there. */
  hideWhenActive?: boolean;
}

export function CustomerPromoterApplicationCard({ hideWhenActive = false }: CustomerPromoterApplicationCardProps = {}) {
  const queryClient = useQueryClient();
  const { data: application, isLoading } = useQuery({
    queryKey: ["customer", "promoter-application"],
    queryFn: fetchMyApplication,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleApply() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile inviare la richiesta. Riprova più tardi."));
      await queryClient.invalidateQueries({ queryKey: ["customer", "promoter-application"] });
      // The access token's own baked-in roles won't show PROMOTER until the
      // next silent refresh -- nudge the area switcher (app-shell.tsx) to
      // re-check live roles right away instead of waiting for that.
      await queryClient.invalidateQueries({ queryKey: ["auth", "me", "roles"] });
    } catch (err: any) {
      setError(err.message || "Impossibile inviare la richiesta. Riprova più tardi.");
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) {
    return <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 animate-pulse h-40" />;
  }

  if (application?.status === "ACTIVE") {
    if (hideWhenActive) return null;
    return (
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Sei un Promoter!</h3>
        <p className="text-sm text-slate-400 light:text-slate-500 mt-2">
          Vai alla dashboard promoter per gestire la tua rete e le tue commissioni, oppure usa il selettore
          &ldquo;Area Cliente / Area Promoter&rdquo; in alto per passare da un&apos;area all&apos;altra in qualsiasi momento.
        </p>
        <Link
          href="/promoter"
          className="inline-block mt-4 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold cursor-pointer"
        >
          Vai alla dashboard Promoter
        </Link>
      </div>
    );
  }

  if (application?.status === "PENDING_APPROVAL") {
    return (
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Lavora con noi</h3>
        <span className="inline-block mt-3 px-3 py-1 rounded-full text-xs font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20">
          In attesa di approvazione
        </span>
        <p className="text-sm text-slate-400 light:text-slate-500 mt-3">
          Il nostro team sta valutando la tua richiesta. Riceverai una notifica non appena verrà esaminata.
        </p>
      </div>
    );
  }

  // Blacklisted: only ever true on a row that already exists (TERMINATED +
  // is_blacklisted, set by an admin -- see network/router.py update_agent).
  // Deliberately does NOT call handleApply -- re-applying while blacklisted
  // would just land in PENDING_APPROVAL server-side anyway (network/service.py
  // apply_as_promoter), but showing that as a normal "in attesa" state here
  // would hide the real reason from someone who has no idea they're blocked.
  if (application?.is_blacklisted) {
    return (
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Lavora con noi</h3>
        <div className="flex gap-3 p-4 mt-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-sm">
          <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <span className="font-semibold block">Il tuo profilo promoter è bloccato</span>
            <span className="text-xs text-rose-300/90 block mt-1">
              Non puoi attivarti come promoter in autonomia. Se pensi sia un errore, contatta subito l&apos;assistenza
              nella sezione Supporto.
            </span>
          </div>
        </div>
        <button
          disabled
          title="Bloccato dall'amministrazione -- contatta il supporto"
          className="mt-4 px-4 py-2 rounded-lg bg-slate-600/30 text-slate-400 text-sm font-semibold cursor-not-allowed opacity-60"
        >
          Lavora con noi
        </button>
      </div>
    );
  }

  // No application yet, or a previous one that's TERMINATED (rejected, or
  // deactivated by an admin) and not blacklisted -- free to (re)try, always
  // auto-activates immediately (network/service.py apply_as_promoter).
  return (
    <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <h3 className="text-lg font-semibold text-white light:text-slate-900">Lavora con noi</h3>
      <p className="text-sm text-slate-400 light:text-slate-500 mt-2">
        Diventa promoter Lial Energy: invita nuovi clienti e guadagna commissioni sulla tua rete.
      </p>
      {application?.status === "TERMINATED" && application.rejection_reason && (
        <p className="text-xs text-slate-500 mt-2">Nota dall&apos;ultima volta: {application.rejection_reason}</p>
      )}
      <button
        onClick={handleApply}
        disabled={submitting}
        className="mt-4 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold cursor-pointer disabled:opacity-50"
      >
        {submitting ? "Attivazione in corso..." : "Lavora con noi"}
      </button>
      {error && <p className="text-xs text-rose-400 mt-2">{error}</p>}
    </div>
  );
}
