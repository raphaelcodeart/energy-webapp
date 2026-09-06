"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { translateErrorDetail } from "@/lib/api-error";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<"checking" | "success" | "error">(token ? "checking" : "error");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/public/verify-email", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ? translateErrorDetail(body.detail) : "Link di conferma non valido.");
        }
        if (!cancelled) setStatus("success");
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || "Link di conferma non valido.");
          setStatus("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="absolute top-1/4 left-1/4 w-72 h-72 bg-orange-600/10 rounded-full blur-3xl -z-10" />
      <div className="absolute bottom-1/4 right-1/4 w-72 h-72 bg-amber-600/10 rounded-full blur-3xl -z-10" />

      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center p-3 rounded-2xl bg-white shadow-lg shadow-orange-500/20 mb-4">
            <Image src="/logo.png" alt="Lial Energy" width={64} height={58} priority />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-8 text-center space-y-3">
          {status === "checking" && (
            <>
              <div className="w-10 h-10 border-2 border-orange-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <h2 className="text-lg font-semibold text-white light:text-slate-900">Conferma in corso...</h2>
            </>
          )}

          {status === "success" && (
            <div className="animate-scale-up space-y-3">
              <svg className="w-12 h-12 text-emerald-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <h2 className="text-lg font-semibold text-white light:text-slate-900">Email confermata</h2>
              <p className="text-sm text-slate-400 light:text-slate-500">
                Il tuo indirizzo email è stato verificato. Ora puoi accedere alla dashboard.
              </p>
              <Link
                href="/login"
                className="inline-block w-full rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 py-3 text-sm font-semibold text-white shadow-lg transition duration-300 mt-2"
              >
                Vai al login
              </Link>
            </div>
          )}

          {status === "error" && (
            <>
              <svg className="w-12 h-12 text-rose-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h2 className="text-lg font-semibold text-white light:text-slate-900">Link non valido</h2>
              <p className="text-sm text-slate-400 light:text-slate-500">
                {error || "Questo link di conferma non è valido o è scaduto."}
              </p>
              <p className="text-xs text-slate-500">
                Puoi richiedere una nuova email di conferma dalla tua dashboard, oppure contattare l&apos;assistenza.
              </p>
              <Link href="/login" className="inline-block text-sm text-orange-400 hover:text-orange-300 transition mt-2">
                Torna al login
              </Link>
            </>
          )}
        </div>
      </div>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
