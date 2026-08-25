"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import type { AgentProfileRead } from "@/lib/types";

async function fetchMyApplication(): Promise<AgentProfileRead | null> {
  const res = await fetch("/api/proxy/network/agents/me");
  if (!res.ok) throw new Error("Impossibile caricare lo stato della richiesta.");
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export function CustomerPromoterApplicationCard() {
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
      if (!res.ok) throw new Error(await res.text());
      await queryClient.invalidateQueries({ queryKey: ["customer", "promoter-application"] });
    } catch {
      setError("Impossibile inviare la richiesta. Riprova più tardi.");
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) {
    return <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 animate-pulse h-40" />;
  }

  // Nessuna richiesta ancora inviata.
  if (!application) {
    return (
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Lavora con noi</h3>
        <p className="text-sm text-slate-400 light:text-slate-500 mt-2">
          Diventa promoter Lial Energy: invita nuovi clienti e guadagna commissioni sulla tua rete.
        </p>
        <button
          onClick={handleApply}
          disabled={submitting}
          className="mt-4 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold cursor-pointer disabled:opacity-50"
        >
          {submitting ? "Invio in corso..." : "Lavora con noi"}
        </button>
        {error && <p className="text-xs text-rose-400 mt-2">{error}</p>}
      </div>
    );
  }

  if (application.status === "PENDING_APPROVAL") {
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

  if (application.status === "ACTIVE") {
    return (
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h3 className="text-lg font-semibold text-white light:text-slate-900">Sei un Promoter!</h3>
        <p className="text-sm text-slate-400 light:text-slate-500 mt-2">
          La tua richiesta è stata approvata. Accedi alla dashboard promoter per gestire la tua rete e le tue commissioni.
        </p>
        <Link
          href="/promoter"
          className="inline-block mt-4 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold cursor-pointer"
        >
          Vai alla dashboard Promoter
        </Link>
        <p className="text-xs text-slate-500 mt-2">
          Se il pulsante non funziona subito, effettua di nuovo l&apos;accesso.
        </p>
      </div>
    );
  }

  // TERMINATED = richiesta rifiutata (soft-delete, mai un hard delete della riga).
  return (
    <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <h3 className="text-lg font-semibold text-white light:text-slate-900">Lavora con noi</h3>
      <div className="flex gap-3 p-4 mt-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
        <div>
          <span className="font-semibold block">Richiesta non approvata</span>
          {application.rejection_reason && (
            <span className="text-xs text-slate-400 light:text-slate-500">{application.rejection_reason}</span>
          )}
        </div>
      </div>
      <button
        onClick={handleApply}
        disabled={submitting}
        className="mt-4 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold cursor-pointer disabled:opacity-50"
      >
        {submitting ? "Invio in corso..." : "Invia una nuova richiesta"}
      </button>
      {error && <p className="text-xs text-rose-400 mt-2">{error}</p>}
    </div>
  );
}
