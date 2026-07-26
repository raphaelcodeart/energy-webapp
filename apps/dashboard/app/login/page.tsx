"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, organizationId }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error ?? "Login fallito");
        return;
      }
      // Redirect to the appropriate dashboard based on email prefix as a heuristic,
      // or simply promoter. The server will restrict dashboard access based on roles.
      if (email.includes("admin") || email.includes("super")) {
        router.push("/admin");
      } else if (email.includes("customer")) {
        router.push("/customer");
      } else {
        router.push("/promoter");
      }
      router.refresh();
    } catch (err: any) {
      setError("Errore di connessione al server");
    } finally {
      setSubmitting(false);
    }
  }

  const fillTestCredentials = (role: "admin" | "promoter" | "customer") => {
    setError(null);
    setPassword("DemoPass123!");
    if (role === "admin") {
      setEmail("admin@lialenergy.demo");
    } else if (role === "promoter") {
      setEmail("promoter@lialenergy.demo");
    } else {
      setEmail("customer@lialenergy.demo");
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 relative">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>

      {/* Background decorations */}
      <div className="absolute top-1/4 left-1/4 w-72 h-72 bg-orange-600/10 rounded-full blur-3xl -z-10 animate-fade-in" />
      <div className="absolute bottom-1/4 right-1/4 w-72 h-72 bg-amber-600/10 rounded-full blur-3xl -z-10 animate-fade-in" />

      <div className="w-full max-w-md animate-scale-up">
        {/* Logo / Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center p-3 rounded-2xl bg-white shadow-lg shadow-orange-500/20 mb-4">
            <Image src="/logo.png" alt="Lial Energy" width={72} height={65} priority />
          </div>
          <p className="text-slate-400 light:text-slate-500 text-sm mt-2">Piattaforma di Gestione Commerciale & Rete</p>
        </div>

        {/* Login Form Card */}
        <form
          onSubmit={handleSubmit}
          className="glass-card rounded-2xl p-8 space-y-5"
        >
          <h2 className="text-xl font-semibold text-white/90 light:text-slate-800">Accedi alla tua area riservata</h2>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase tracking-wider" htmlFor="organizationId">
              ID Organizzazione
            </label>
            <input
              id="organizationId"
              className="w-full rounded-xl glass-input px-4 py-3 text-sm focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
              value={organizationId}
              onChange={(e) => setOrganizationId(e.target.value)}
              placeholder="Inserisci il codice UUID dell'organizzazione"
              required
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase tracking-wider" htmlFor="email">
              Indirizzo Email
            </label>
            <input
              id="email"
              type="email"
              className="w-full rounded-xl glass-input px-4 py-3 text-sm focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nome@lialenergy.demo"
              required
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase tracking-wider" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="w-full rounded-xl glass-input px-4 py-3 text-sm focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
            <div className="text-right">
              <Link href="/forgot-password" className="text-xs text-slate-400 hover:text-orange-400 transition">
                Password dimenticata?
              </Link>
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2.5 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm animate-fade-in">
              <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-xl bg-gradient-to-r from-orange-600 to-amber-600 hover:from-orange-500 hover:to-amber-500 py-3 text-sm font-semibold text-white shadow-lg hover:shadow-orange-600/30 transition-all duration-300 disabled:opacity-50 disabled:pointer-events-none cursor-pointer mt-2"
          >
            {submitting ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-5 w-5 text-white light:text-slate-900" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Verifica credenziali...
              </span>
            ) : (
              "Accedi al sistema"
            )}
          </button>
        </form>

        {/* Demo Helper Panel */}
        <div className="glass-card rounded-2xl p-6 mt-6 border-amber-500/10">
          <h3 className="text-sm font-semibold text-amber-400 flex items-center gap-2 mb-3">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Area Demo & Test
          </h3>
          <p className="text-slate-400 light:text-slate-500 text-xs mb-4">
            Usa l&apos;ID Organizzazione stampato dal seed backend. Fai click su uno dei ruoli per precompilare Email e Password (<code>DemoPass123!</code>):
          </p>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => fillTestCredentials("admin")}
              className="py-2 px-3 text-xs bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 hover:bg-orange-500/20 hover:border-orange-500/30 rounded-lg text-slate-300 light:text-slate-600 font-medium transition cursor-pointer"
            >
              Amministratore
            </button>
            <button
              type="button"
              onClick={() => fillTestCredentials("promoter")}
              className="py-2 px-3 text-xs bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 hover:bg-amber-500/20 hover:border-amber-500/30 rounded-lg text-slate-300 light:text-slate-600 font-medium transition cursor-pointer"
            >
              Promoter
            </button>
            <button
              type="button"
              onClick={() => fillTestCredentials("customer")}
              className="py-2 px-3 text-xs bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 hover:bg-emerald-500/20 hover:border-emerald-500/30 rounded-lg text-slate-300 light:text-slate-600 font-medium transition cursor-pointer"
            >
              Cliente
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
