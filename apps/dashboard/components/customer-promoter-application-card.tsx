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

const COLLABORATION_CONTRACT_TEXT = `Accettando questo contratto di collaborazione, dichiari di voler diventare Promoter Lial Energy e di aver preso visione delle condizioni di collaborazione: promuoverai i prodotti e servizi Lial Energy nel rispetto della normativa vigente e del codice di condotta aziendale, e riceverai le commissioni maturate secondo il piano provvigionale in vigore, accreditate sul tuo wallet Lial Energy. La collaborazione non costituisce rapporto di lavoro subordinato ed è revocabile in qualsiasi momento da entrambe le parti.`;

export function CustomerPromoterApplicationCard({ hideWhenActive = false }: CustomerPromoterApplicationCardProps = {}) {
  const queryClient = useQueryClient();
  const { data: application, isLoading } = useQuery({
    queryKey: ["customer", "promoter-application"],
    queryFn: fetchMyApplication,
  });
  const [modalOpen, setModalOpen] = useState(false);
  const [acceptContract, setAcceptContract] = useState(false);
  const [otpRequested, setOtpRequested] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openModal() {
    setAcceptContract(false);
    setOtpRequested(false);
    setOtpCode("");
    setError(null);
    setModalOpen(true);
  }

  async function handleRequestOtp() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/apply/request-otp", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile inviare il codice. Riprova più tardi."));
      setOtpRequested(true);
    } catch (err: any) {
      setError(err.message || "Impossibile inviare il codice. Riprova più tardi.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApply() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accept_contract: acceptContract, otp_code: otpCode }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile inviare la richiesta. Riprova più tardi."));
      await queryClient.invalidateQueries({ queryKey: ["customer", "promoter-application"] });
      // The access token's own baked-in roles won't show PROMOTER until the
      // next silent refresh -- nudge the area switcher (app-shell.tsx) to
      // re-check live roles right away instead of waiting for that.
      await queryClient.invalidateQueries({ queryKey: ["auth", "me", "roles"] });
      setModalOpen(false);
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
        onClick={openModal}
        className="mt-4 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold cursor-pointer"
      >
        Lavora con noi
      </button>

      {modalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm px-4 py-8 overflow-y-auto">
          <div className="w-full max-w-md glass-card rounded-2xl p-6 my-auto animate-scale-up">
            <h3 className="text-base font-semibold text-white light:text-slate-900 mb-3">Diventa Promoter Lial Energy</h3>

            <div className="max-h-40 overflow-y-auto rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200 p-3 text-xs text-slate-400 light:text-slate-600 leading-relaxed mb-3">
              {COLLABORATION_CONTRACT_TEXT}
            </div>

            <label className="flex items-start gap-2.5 text-xs text-slate-300 light:text-slate-600 cursor-pointer mb-4">
              <input
                type="checkbox"
                checked={acceptContract}
                onChange={(e) => setAcceptContract(e.target.checked)}
                className="mt-0.5 w-4 h-4 rounded border-white/20 accent-orange-500 shrink-0"
              />
              <span>Ho letto e accetto il contratto di collaborazione.</span>
            </label>

            {!otpRequested ? (
              <button
                onClick={handleRequestOtp}
                disabled={!acceptContract || submitting}
                className="w-full rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 py-2.5 text-sm font-semibold text-white shadow-lg transition duration-300 disabled:opacity-50 cursor-pointer"
              >
                {submitting ? "Invio codice..." : "Invia codice di conferma via email"}
              </button>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-slate-400 light:text-slate-500">
                  Ti abbiamo inviato un codice via email. Inseriscilo qui sotto per confermare la tua richiesta.
                </p>
                <input
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="Codice a 6 cifre"
                  inputMode="numeric"
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm text-center tracking-[0.3em] font-mono focus:border-orange-500"
                />
                <button
                  onClick={handleApply}
                  disabled={otpCode.length !== 6 || submitting}
                  className="w-full rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 py-2.5 text-sm font-semibold text-white shadow-lg transition duration-300 disabled:opacity-50 cursor-pointer"
                >
                  {submitting ? "Conferma in corso..." : "Conferma e attiva"}
                </button>
                <button
                  onClick={handleRequestOtp}
                  disabled={submitting}
                  className="w-full text-xs text-orange-400 hover:text-orange-300 transition cursor-pointer disabled:opacity-50"
                >
                  Non hai ricevuto il codice? Invia di nuovo
                </button>
              </div>
            )}

            {error && <p className="text-xs text-rose-400 mt-3">{error}</p>}

            <button
              onClick={() => setModalOpen(false)}
              className="w-full mt-3 text-xs text-slate-500 hover:text-slate-300 transition cursor-pointer"
            >
              Annulla
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
