"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { WalletRead, WalletTransactionRead } from "@/lib/types";

const CASHBACK_SOURCES = new Set([
  "ORDER_CASHBACK_BASE", "ORDER_CASHBACK_BONUS", "INVOICE_REDEMPTION_BASE", "INVOICE_REDEMPTION_BONUS",
]);

/** Counts a number up from its previous value to `value` over `durationMs`,
    eased -- used so the wallet/cashback figures on the dashboard home feel
    alive instead of just appearing, without pulling in an animation
    library for one effect. Re-triggers whenever `value` changes (e.g. a
    fresh accredit lands and refetches). */
function useCountUp(value: number, durationMs = 900): number {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const from = fromRef.current;
    const to = value;
    if (from === to) return;
    const start = performance.now();
    function tick(now: number) {
      const progress = Math.min((now - start) / durationMs, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out-cubic
      setDisplay(Math.round(from + (to - from) * eased));
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    }
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return display;
}

function formatLialCash(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function fetchMyWallet(): Promise<WalletRead> {
  const res = await fetch("/api/proxy/wallets/me");
  if (!res.ok) throw new Error("Impossibile caricare il wallet.");
  return res.json();
}

async function fetchMyTransactions(): Promise<WalletTransactionRead[]> {
  const res = await fetch("/api/proxy/wallets/me/transactions");
  if (!res.ok) throw new Error("Impossibile caricare le transazioni.");
  return res.json();
}

/** One glowing, animated stat card -- balance/cashback figures on the
    dashboard home are the first numbers a customer or promoter sees, so
    they get a bolder, more "alive" treatment than a plain table row. */
function StatCard({
  label, cents, tone, icon, hint,
}: {
  label: string;
  cents: number;
  tone: "orange" | "emerald" | "sky";
  icon: React.ReactNode;
  hint?: string;
}) {
  const animated = useCountUp(cents);
  const toneClasses: Record<"orange" | "emerald" | "sky", { ring: string; glow: string; text: string; iconBg: string }> = {
    orange: { ring: "from-orange-500/20 via-orange-500/5", glow: "shadow-orange-500/10", text: "text-orange-400", iconBg: "bg-orange-500/15 text-orange-400" },
    emerald: { ring: "from-emerald-500/20 via-emerald-500/5", glow: "shadow-emerald-500/10", text: "text-emerald-400", iconBg: "bg-emerald-500/15 text-emerald-400" },
    sky: { ring: "from-sky-500/20 via-sky-500/5", glow: "shadow-sky-500/10", text: "text-sky-400", iconBg: "bg-sky-500/15 text-sky-400" },
  };
  const t = toneClasses[tone];

  return (
    <div
      className={`relative overflow-hidden rounded-2xl border border-white/10 light:border-slate-200 bg-gradient-to-br ${t.ring} to-transparent bg-slate-950/60 light:bg-white/80 p-5 shadow-lg ${t.glow} transition-transform hover:-translate-y-0.5`}
    >
      <div className="flex items-start justify-between mb-4">
        <span className={`p-2.5 rounded-xl ${t.iconBg}`}>{icon}</span>
      </div>
      <p className="text-[10px] font-bold text-slate-400 light:text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-3xl font-black tabular-nums ${t.text}`}>
        {formatLialCash(animated)} <span className="text-sm font-bold align-top">LialCash</span>
      </p>
      {hint && <p className="text-[11px] text-slate-500 mt-1.5">{hint}</p>}
    </div>
  );
}

/** Wallet balance + cashback earned/spent, animated -- the dashboard-home
    version of the wallet numbers (full history/CSV export stays in the
    Wallet/Contabilità tabs, this is just the at-a-glance summary). Shared
    between the customer and promoter home screens. */
export function DashboardWalletStats() {
  const { data: wallet } = useQuery({ queryKey: ["wallet", "me"], queryFn: fetchMyWallet });
  const { data: transactions } = useQuery({ queryKey: ["wallet", "me", "transactions"], queryFn: fetchMyTransactions });

  const list = transactions ?? [];
  const cashbackEarnedCents = list
    .filter((t) => t.source && CASHBACK_SOURCES.has(t.source))
    .reduce((sum, t) => sum + t.amount_cents, 0);
  const spentCents = wallet
    ? list
        .filter((t) => t.from_wallet_id === wallet.id)
        .reduce((sum, t) => sum + t.amount_cents, 0)
    : 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <StatCard
        label="Saldo Wallet"
        cents={wallet?.balance_cents ?? 0}
        tone="orange"
        hint="Disponibile per i tuoi acquisti"
        icon={
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
          </svg>
        }
      />
      <StatCard
        label="Cashback Accumulato"
        cents={cashbackEarnedCents}
        tone="emerald"
        hint="Totale ricevuto da ordini e riscatti"
        icon={
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2" />
          </svg>
        }
      />
      <StatCard
        label="LialCash Consumati"
        cents={spentCents}
        tone="sky"
        hint="Totale speso in acquisti e trasferimenti"
        icon={
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3v-6m-3 6v-1m6-13H9a2 2 0 00-2 2v14a2 2 0 002 2h6a2 2 0 002-2V6a2 2 0 00-2-2z" />
          </svg>
        }
      />
    </div>
  );
}
