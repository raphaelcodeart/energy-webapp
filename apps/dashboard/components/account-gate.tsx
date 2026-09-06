"use client";

import { useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { translateErrorDetail } from "@/lib/api-error";

interface MeRead {
  roles: string[];
  email_verified: boolean;
  profile_complete: boolean;
  privacy_accepted: boolean;
}

async function fetchMe(): Promise<MeRead | null> {
  const res = await fetch("/api/proxy/auth/me");
  if (!res.ok) return null;
  return res.json();
}

const PROVINCES = [
  "AG", "AL", "AN", "AO", "AR", "AP", "AT", "AV", "BA", "BT", "BL", "BN", "BG", "BI", "BO", "BZ", "BS", "BR",
  "CA", "CL", "CB", "CI", "CE", "CT", "CZ", "CH", "CO", "CS", "CR", "KR", "CN", "EN", "FM", "FE", "FI", "FG",
  "FC", "FR", "GE", "GO", "GR", "IM", "IS", "SP", "LT", "LE", "LC", "LI", "LO", "LU", "MC", "MN", "MS", "MT",
  "VS", "ME", "MI", "MO", "MB", "NA", "NO", "NU", "OG", "OT", "OR", "PD", "PA", "PR", "PC", "PE", "PG", "PU",
  "PV", "PZ", "PN", "PO", "RG", "RA", "RC", "RE", "RI", "RN", "RM", "RO", "SA", "SS", "SV", "SI", "SR", "SO",
  "TA", "TE", "TR", "TO", "TP", "UD", "VA", "VE", "VB", "VC", "VR", "VV", "VI", "VT",
];

function ProfileCompletionForm({ onComplete }: { onComplete: () => void }) {
  const [fiscalCode, setFiscalCode] = useState("");
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [province, setProvince] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/proxy/auth/me/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fiscal_code: fiscalCode,
          residence_street: street,
          residence_city: city,
          residence_province: province,
          residence_postal_code: postalCode,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ? translateErrorDetail(body.detail) : "Impossibile salvare i dati.");
      }
      onComplete();
    } catch (err: any) {
      setError(err.message || "Impossibile salvare i dati.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1">
        <label className="text-[11px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice Fiscale</label>
        <input
          required minLength={11} maxLength={16} value={fiscalCode}
          onChange={(e) => setFiscalCode(e.target.value.toUpperCase())}
          placeholder="RSSMRA80A01H501U"
          className="w-full rounded-xl glass-input px-3 py-2.5 text-sm uppercase focus:border-orange-500"
        />
      </div>
      <div className="space-y-1">
        <label className="text-[11px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Indirizzo di residenza</label>
        <input
          required value={street} onChange={(e) => setStreet(e.target.value)}
          placeholder="Via/Piazza e numero civico"
          className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
        />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2 space-y-1">
          <label className="text-[11px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Città</label>
          <input
            required value={city} onChange={(e) => setCity(e.target.value)}
            className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-[11px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Prov.</label>
          <select
            required value={province} onChange={(e) => setProvince(e.target.value)}
            className="w-full rounded-xl glass-input px-2 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
          >
            <option value="" disabled>--</option>
            {PROVINCES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="space-y-1">
        <label className="text-[11px] font-semibold text-slate-300 light:text-slate-600 uppercase block">CAP</label>
        <input
          required minLength={5} maxLength={5} value={postalCode}
          onChange={(e) => setPostalCode(e.target.value.replace(/\D/g, ""))}
          className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
        />
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{error}</div>
      )}

      <button
        type="submit" disabled={submitting}
        className="w-full rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 py-3 text-sm font-semibold text-white shadow-lg transition duration-300 disabled:opacity-50 cursor-pointer"
      >
        {submitting ? "Salvataggio..." : "Continua"}
      </button>
    </form>
  );
}

function EmailVerificationGate({ email }: { email?: string }) {
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

  async function handleResend() {
    setSending(true);
    try {
      await fetch("/api/proxy/auth/resend-verification", { method: "POST" });
      setSent(true);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="text-center space-y-4">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-500/10 text-orange-400">
        <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      </div>
      <div>
        <h3 className="text-base font-semibold text-white light:text-slate-900">Conferma il tuo indirizzo email</h3>
        <p className="text-sm text-slate-400 light:text-slate-500 mt-1">
          {email ? <>Ti abbiamo inviato un link di conferma a <strong className="text-slate-200 light:text-slate-700">{email}</strong>.</> : "Controlla la tua casella di posta."}
          {" "}Clicca il link per attivare l&apos;accesso alla dashboard.
        </p>
      </div>
      {sent ? (
        <p className="text-xs text-emerald-400">Email inviata di nuovo -- controlla anche lo spam.</p>
      ) : (
        <button
          onClick={handleResend} disabled={sending}
          className="text-sm text-orange-400 hover:text-orange-300 transition cursor-pointer disabled:opacity-50"
        >
          {sending ? "Invio in corso..." : "Non hai ricevuto l'email? Invia di nuovo"}
        </button>
      )}
    </div>
  );
}

/** Blocks the whole dashboard behind a modal until the account satisfies the
 * mandatory gates (see docs/business-rules.md#account-gates): email
 * verification (new registrations only -- existing accounts are
 * grandfathered, see the 0026 migration) and fiscal-code/residence profile
 * completion (retroactive for every account, an explicit product decision).
 * Admin-tier roles are exempt -- these gates only make sense for a
 * self-registered CUSTOMER/PROMOTER. */
export function AccountGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { data: me, isLoading } = useQuery({
    queryKey: ["auth", "me", "gate"],
    queryFn: fetchMe,
    staleTime: 30_000,
  });

  if (isLoading || !me) return <>{children}</>;

  const isGateable = me.roles.includes("CUSTOMER") || me.roles.includes("PROMOTER");
  if (!isGateable) return <>{children}</>;

  const blocked = !me.email_verified || !me.profile_complete;
  if (!blocked) return <>{children}</>;

  function handleProfileComplete() {
    queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
  }

  return (
    <>
      <div aria-hidden className="pointer-events-none select-none blur-sm opacity-40">{children}</div>
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm px-4 py-8 overflow-y-auto">
        <div className="w-full max-w-md glass-card rounded-2xl p-8 my-auto animate-scale-up">
          {!me.email_verified ? (
            <EmailVerificationGate />
          ) : (
            <>
              <div className="mb-6 text-center">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-500/10 text-orange-400 mb-3">
                  <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
                <h3 className="text-base font-semibold text-white light:text-slate-900">Completa il tuo profilo</h3>
                <p className="text-sm text-slate-400 light:text-slate-500 mt-1">
                  Per usare la dashboard ci servono ancora il tuo codice fiscale e l&apos;indirizzo di residenza.
                </p>
              </div>
              <ProfileCompletionForm onComplete={handleProfileComplete} />
            </>
          )}
        </div>
      </div>
    </>
  );
}
