"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";

type WelcomeBonusStatus = { available: boolean; amount_cents: number };

function lialCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 2 })} LialCash`;
}

async function fetchWelcomeBonus(): Promise<WelcomeBonusStatus> {
  const res = await fetch("/api/proxy/wallets/me/welcome-bonus");
  if (!res.ok) throw new Error("Impossibile verificare l'omaggio di benvenuto.");
  return res.json();
}

/** "Riscatta il tuo omaggio": the one-off welcome bonus, shown on the
    dashboard home until it's claimed and then never again. `available`
    is false both before the claim exists and forever after (see
    wallets/schemas.py::WelcomeBonusStatusRead), so this component simply
    renders nothing when it's false -- there is no "already claimed" state
    to design for.

    Claiming is idempotent server-side (the idempotency key is derived from
    the user id), so a double-click can't mint a second bonus even if the
    button's own disabled state were bypassed. */
export function WelcomeBonusCard() {
  const queryClient = useQueryClient();
  const { data: bonus } = useQuery({
    queryKey: ["wallet", "welcome-bonus"],
    queryFn: fetchWelcomeBonus,
  });

  const [claiming, setClaiming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justClaimed, setJustClaimed] = useState(false);

  async function handleClaim() {
    setClaiming(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/wallets/me/welcome-bonus/claim", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setJustClaimed(true);
      // Refresh everything the new credit touches: the bonus status itself
      // (so the card disappears), the wallet balance, and the home stat
      // cards that read from both.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["wallet"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting"] }),
      ]);
    } catch (err: any) {
      setError(err.message || "Impossibile riscattare l'omaggio.");
      setClaiming(false);
    }
  }

  // Success flash, shown briefly in place of the card before it goes for good.
  if (justClaimed) {
    return (
      <div className="rounded-2xl p-5 border border-emerald-500/30 bg-gradient-to-br from-emerald-500/15 to-transparent flex items-center gap-4 animate-scale-up">
        <span className="p-3 rounded-xl bg-emerald-500/20 text-emerald-400 shrink-0">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </span>
        <div>
          <p className="text-sm font-bold text-white light:text-slate-900">Omaggio riscattato!</p>
          <p className="text-xs text-slate-400 light:text-slate-500">
            {lialCash(bonus?.amount_cents ?? 0)} sono già disponibili sul tuo wallet.
          </p>
        </div>
      </div>
    );
  }

  if (!bonus?.available) return null;

  return (
    <div className="relative overflow-hidden rounded-2xl p-5 border border-orange-500/30 bg-gradient-to-br from-orange-500/15 via-amber-500/5 to-transparent">
      {/* Decorative glow -- pointer-events-none so it never eats the click. */}
      <div className="pointer-events-none absolute -top-10 -right-10 w-40 h-40 rounded-full bg-orange-500/20 blur-3xl" />
      <div className="relative flex flex-col sm:flex-row sm:items-center gap-4">
        <span className="p-3 rounded-xl bg-orange-500/20 text-orange-400 shrink-0 w-fit">
          <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zM5 12h14M5 12a2 2 0 110-4h14a2 2 0 110 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7" />
          </svg>
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-white light:text-slate-900">
            Il tuo omaggio di benvenuto ti aspetta
          </p>
          <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">
            Ricevi <strong className="text-orange-400">{lialCash(bonus.amount_cents)}</strong> sul tuo
            wallet, da usare subito per i tuoi acquisti. Puoi riscattarlo una sola volta.
          </p>
          {error && <p className="text-xs text-rose-400 mt-1.5">{error}</p>}
        </div>
        <button
          onClick={handleClaim}
          disabled={claiming}
          className="shrink-0 px-5 py-2.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-white text-xs font-bold shadow-lg shadow-orange-500/20 transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
        >
          {claiming ? "Riscatto in corso..." : "Riscatta il tuo omaggio"}
        </button>
      </div>
    </div>
  );
}
