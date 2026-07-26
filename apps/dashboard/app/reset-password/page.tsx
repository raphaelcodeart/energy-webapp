"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("Le due password non coincidono.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/public/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Impossibile reimpostare la password.");
      }
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (err: any) {
      setError(err.message || "Impossibile reimpostare la password.");
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
          {!token ? (
            <div className="text-center space-y-3">
              <h2 className="text-lg font-semibold text-white light:text-slate-900">Link non valido</h2>
              <p className="text-sm text-slate-400 light:text-slate-500">
                Questo link di reimpostazione non è valido. Richiedine uno nuovo.
              </p>
              <Link href="/forgot-password" className="inline-block text-sm text-orange-400 hover:text-orange-300 transition mt-2">
                Richiedi un nuovo link
              </Link>
            </div>
          ) : success ? (
            <div className="text-center space-y-3 animate-scale-up">
              <svg className="w-12 h-12 text-emerald-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <h2 className="text-lg font-semibold text-white light:text-slate-900">Password aggiornata</h2>
              <p className="text-sm text-slate-400 light:text-slate-500">Verrai reindirizzato al login...</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <h2 className="text-xl font-semibold text-white/90 light:text-slate-800">Scegli una nuova password</h2>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase tracking-wider">Nuova Password</label>
                <input required type="password" minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Almeno 8 caratteri"
                  className="w-full rounded-xl glass-input px-4 py-3 text-sm focus:border-orange-500" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase tracking-wider">Ripeti Password</label>
                <input required type="password" minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Ripeti la password"
                  className={`w-full rounded-xl glass-input px-4 py-3 text-sm focus:border-orange-500 ${
                    confirmPassword && newPassword !== confirmPassword ? "border-rose-500/50" : ""
                  }`} />
                {confirmPassword && newPassword !== confirmPassword && (
                  <p className="text-[11px] text-rose-400">Le password non coincidono.</p>
                )}
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{error}</div>
              )}

              <button type="submit" disabled={submitting}
                className="w-full rounded-xl bg-gradient-to-r from-orange-600 to-amber-600 hover:from-orange-500 hover:to-amber-500 py-3 text-sm font-semibold text-white shadow-lg transition-all duration-300 disabled:opacity-50 cursor-pointer">
                {submitting ? "Salvataggio..." : "Reimposta Password"}
              </button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
