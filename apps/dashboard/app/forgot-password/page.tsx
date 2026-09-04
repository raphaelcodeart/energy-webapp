"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { translateErrorDetail } from "@/lib/api-error";
import { DEFAULT_ORGANIZATION_ID } from "@/lib/config";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/public/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: DEFAULT_ORGANIZATION_ID, email }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ? translateErrorDetail(body.detail) : "Richiesta non riuscita.");
      }
      setSubmitted(true);
    } catch (err: any) {
      setError(err.message || "Richiesta non riuscita.");
    } finally {
      setSubmitting(false);
    }
  }

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

        <div className="glass-card rounded-2xl p-8">
          {submitted ? (
            <div className="text-center space-y-3">
              <svg className="w-12 h-12 text-emerald-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <h2 className="text-lg font-semibold text-white light:text-slate-900">Controlla la tua email</h2>
              <p className="text-sm text-slate-400 light:text-slate-500">
                Se l&apos;indirizzo inserito corrisponde a un account esistente, riceverai un link per reimpostare la password entro qualche minuto.
              </p>
              <Link href="/login" className="inline-block text-sm text-orange-400 hover:text-orange-300 transition mt-2">
                Torna al login
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <h2 className="text-xl font-semibold text-white/90 light:text-slate-800">Password dimenticata</h2>
                <p className="text-sm text-slate-400 light:text-slate-500 mt-1">
                  Inserisci la tua email: ti invieremo un link per reimpostare la password.
                </p>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase tracking-wider">Email</label>
                <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl glass-input px-4 py-3 text-sm focus:border-orange-500" />
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{error}</div>
              )}

              <button type="submit" disabled={submitting}
                className="w-full rounded-xl bg-gradient-to-r from-orange-600 to-amber-600 hover:from-orange-500 hover:to-amber-500 py-3 text-sm font-semibold text-white shadow-lg transition-all duration-300 disabled:opacity-50 cursor-pointer">
                {submitting ? "Invio in corso..." : "Invia link di reimpostazione"}
              </button>

              <Link href="/login" className="block text-center text-xs text-slate-400 hover:text-white light:hover:text-slate-900 transition">
                Torna al login
              </Link>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
