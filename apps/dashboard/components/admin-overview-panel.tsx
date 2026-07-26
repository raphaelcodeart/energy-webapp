"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  AttentionItem,
  DashboardSummary,
  RecentActivityItem,
  TimeseriesPoint,
} from "@/lib/types";

type PeriodKey = "today" | "7d" | "month" | "quarter" | "year";

const PERIODS: { key: PeriodKey; label: string; days: number }[] = [
  { key: "today", label: "Oggi", days: 1 },
  { key: "7d", label: "7 giorni", days: 7 },
  { key: "month", label: "Mese", days: 30 },
  { key: "quarter", label: "Trimestre", days: 90 },
  { key: "year", label: "Anno", days: 365 },
];

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
};

const ACTION_LABELS: Record<string, string> = {
  "login.success": "Accesso effettuato",
  "contract.transition": "Cambio stato contratto",
  "contract.create": "Contratto creato",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function periodBounds(days: number): { period_from: string; period_to: string } {
  const to = new Date();
  const from = new Date(to.getTime() - days * 24 * 60 * 60 * 1000);
  return { period_from: from.toISOString().slice(0, 10), period_to: to.toISOString().slice(0, 10) };
}

async function fetchSummary(days: number): Promise<DashboardSummary> {
  const { period_from, period_to } = periodBounds(days);
  const res = await fetch(`/api/proxy/reports/dashboard-summary?period_from=${period_from}&period_to=${period_to}`);
  if (!res.ok) throw new Error("Impossibile caricare il riepilogo.");
  return res.json();
}

async function fetchContractsTimeseries(): Promise<TimeseriesPoint[]> {
  const res = await fetch("/api/proxy/reports/contracts-timeseries?months=12");
  if (!res.ok) throw new Error("Impossibile caricare l'andamento contratti.");
  return res.json();
}

async function fetchCommissionsTimeseries(): Promise<TimeseriesPoint[]> {
  const res = await fetch("/api/proxy/reports/commissions-timeseries?months=12");
  if (!res.ok) throw new Error("Impossibile caricare l'andamento provvigioni.");
  return res.json();
}

async function fetchAttentionItems(): Promise<AttentionItem[]> {
  const res = await fetch("/api/proxy/reports/attention-items");
  if (!res.ok) throw new Error("Impossibile caricare le segnalazioni.");
  return res.json();
}

async function fetchRecentActivity(): Promise<RecentActivityItem[]> {
  const res = await fetch("/api/proxy/reports/recent-activity?limit=10");
  if (!res.ok) throw new Error("Impossibile caricare l'attività recente.");
  return res.json();
}

function monthLabel(period: string): string {
  const [y, m] = period.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString("it-IT", { month: "short" });
}

function KpiCard({
  label,
  value,
  accent,
  icon,
}: {
  label: string;
  value: string;
  accent: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 flex items-center gap-4">
      <div className={`p-3 rounded-xl shrink-0 ${accent}`}>{icon}</div>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1 truncate">{label}</p>
        <p className="text-xl font-bold text-white light:text-slate-900 truncate">{value}</p>
      </div>
    </div>
  );
}

const QUICK_LINKS: {
  key: string;
  label: string;
  description: string;
  icon: React.ReactNode;
}[] = [
  {
    key: "list",
    label: "Contratti",
    description: "Gestisci tutti i contratti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
      </svg>
    ),
  },
  {
    key: "create",
    label: "Nuovo Contratto",
    description: "Crea una nuova proposta",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 4v16m8-8H4" />
      </svg>
    ),
  },
  {
    key: "customers",
    label: "Clienti",
    description: "Anagrafiche clienti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    key: "promoters",
    label: "Promoter",
    description: "Rete e collaboratori",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
      </svg>
    ),
  },
  {
    key: "products",
    label: "Prodotti",
    description: "Marketplace & catalogo",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
];

export function AdminOverviewPanel({ onNavigate }: { onNavigate?: (key: string) => void }) {
  const [period, setPeriod] = useState<PeriodKey>("month");
  const activeDays = PERIODS.find((p) => p.key === period)!.days;

  const { data: summary, error: summaryError, isLoading: summaryLoading } = useQuery({
    queryKey: ["admin", "reports", "summary", activeDays],
    queryFn: () => fetchSummary(activeDays),
  });
  const { data: contractsSeries } = useQuery({
    queryKey: ["admin", "reports", "contracts-timeseries"],
    queryFn: fetchContractsTimeseries,
  });
  const { data: commissionsSeries } = useQuery({
    queryKey: ["admin", "reports", "commissions-timeseries"],
    queryFn: fetchCommissionsTimeseries,
  });
  const { data: attentionItems } = useQuery({
    queryKey: ["admin", "reports", "attention-items"],
    queryFn: fetchAttentionItems,
  });
  const { data: recentActivity } = useQuery({
    queryKey: ["admin", "reports", "recent-activity"],
    queryFn: fetchRecentActivity,
  });

  const contractsChartData = (contractsSeries ?? []).map((p) => ({ ...p, label: monthLabel(p.period) }));
  const commissionsChartData = (commissionsSeries ?? []).map((p) => ({
    ...p,
    label: monthLabel(p.period),
    euro: p.value / 100,
  }));

  return (
    <div className="space-y-6">
      {/* Quick-access section shortcuts -- large, unmissable buttons so the most
          common admin destinations are one click away without hunting in the
          sidebar. */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {QUICK_LINKS.map((link) => (
          <button
            key={link.key}
            onClick={() => onNavigate?.(link.key)}
            className="group flex flex-col items-start gap-3 p-4 rounded-2xl border border-white/5 light:border-slate-200 bg-gradient-to-br from-slate-900/60 to-slate-900/20 light:from-white light:to-slate-50 hover:border-orange-500/40 hover:shadow-lg hover:shadow-orange-500/10 transition-all duration-200 cursor-pointer text-left"
          >
            <span className="p-2.5 rounded-xl bg-orange-500/10 text-orange-400 group-hover:bg-orange-500 group-hover:text-white transition-colors">
              {link.icon}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-white light:text-slate-900 truncate">
                {link.label}
              </span>
              <span className="block text-[11px] text-slate-500 truncate">{link.description}</span>
            </span>
          </button>
        ))}
      </div>

      {/* Time filter */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {PERIODS.map((p) => (
          <button
            key={p.key}
            onClick={() => setPeriod(p.key)}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition cursor-pointer border ${
              period === p.key
                ? "bg-gradient-to-r from-orange-600 to-amber-500 text-white border-transparent shadow-lg shadow-orange-500/20"
                : "bg-white/5 light:bg-slate-900/5 text-slate-400 light:text-slate-500 border-white/5 light:border-slate-200 hover:bg-white/10"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {summaryError && (
        <p className="text-sm text-rose-400">Impossibile caricare il riepilogo. Riprova più tardi.</p>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Contratti totali"
          value={summaryLoading ? "…" : String(summary?.contracts.total ?? 0)}
          accent="bg-orange-500/10 text-orange-400"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
            </svg>
          }
        />
        <KpiCard
          label="Contratti attivi"
          value={summaryLoading ? "…" : String(summary?.contracts.active ?? 0)}
          accent="bg-emerald-500/10 text-emerald-400"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          }
        />
        <KpiCard
          label="In attesa di approvazione"
          value={summaryLoading ? "…" : String(summary?.contracts.pending_approval ?? 0)}
          accent="bg-amber-500/10 text-amber-400"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <KpiCard
          label="Respinti / cessati"
          value={
            summaryLoading
              ? "…"
              : String((summary?.contracts.rejected ?? 0) + (summary?.contracts.cancelled ?? 0))
          }
          accent="bg-rose-500/10 text-rose-400"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          }
        />
        <KpiCard
          label="Provvigioni maturate"
          value={summaryLoading ? "…" : euro(summary?.commissions.accrued_cents ?? 0)}
          accent="bg-sky-500/10 text-sky-400"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2" />
            </svg>
          }
        />
        <KpiCard
          label="Provvigioni pagate"
          value={summaryLoading ? "…" : euro(summary?.commissions.paid_cents ?? 0)}
          accent="bg-emerald-500/10 text-emerald-400"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a4 4 0 00-8 0v2m-2 0h12a2 2 0 012 2v7a2 2 0 01-2 2H7a2 2 0 01-2-2v-7a2 2 0 012-2z" />
            </svg>
          }
        />
        <KpiCard
          label="Promoter attivi"
          value={summaryLoading ? "…" : String(summary?.active_promoters ?? 0)}
          accent="bg-orange-500/10 text-orange-400"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
            </svg>
          }
        />
        <KpiCard
          label="Clienti attivi"
          value={summaryLoading ? "…" : String(summary?.active_customers ?? 0)}
          accent="bg-sky-500/10 text-sky-400"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          }
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-4">Andamento contratti (12 mesi)</h4>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={contractsChartData}>
              <defs>
                <linearGradient id="contractsGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f97316" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#64748b" strokeOpacity={0.15} vertical={false} />
              <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }}
                labelStyle={{ color: "#e2e8f0" }}
                formatter={(value) => [String(value), "Contratti"]}
              />
              <Area type="monotone" dataKey="value" stroke="#f97316" strokeWidth={2} fill="url(#contractsGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-4">Andamento provvigioni (12 mesi)</h4>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={commissionsChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#64748b" strokeOpacity={0.15} vertical={false} />
              <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }}
                labelStyle={{ color: "#e2e8f0" }}
                formatter={(value) => [euro(Math.round(Number(value) * 100)), "Provvigioni"]}
              />
              <Bar dataKey="euro" fill="#0ea5e9" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Attention items + recent activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-4">Richiede attenzione</h4>
          <div className="space-y-2">
            {attentionItems === undefined ? (
              <p className="text-xs text-slate-500 py-4 text-center">Caricamento...</p>
            ) : attentionItems.length === 0 ? (
              <p className="text-xs text-slate-500 py-4 text-center">Nessuna anomalia rilevata.</p>
            ) : (
              attentionItems.map((item) => (
                <div
                  key={item.contract_id}
                  className="flex items-center justify-between p-3 rounded-xl bg-amber-500/5 border border-amber-500/15"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-mono text-white light:text-slate-900 truncate">{item.contract_id}</p>
                    <p className="text-[11px] text-amber-400">
                      {STATUS_LABELS[item.status] ?? item.status} · {item.days_in_status}g
                    </p>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20 shrink-0">
                    Verifica
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-4">Attività recente</h4>
          <div className="space-y-2">
            {recentActivity === undefined ? (
              <p className="text-xs text-slate-500 py-4 text-center">Caricamento...</p>
            ) : recentActivity.length === 0 ? (
              <p className="text-xs text-slate-500 py-4 text-center">Nessuna attività registrata.</p>
            ) : (
              recentActivity.map((item) => (
                <div key={item.id} className="flex items-center justify-between p-3 rounded-xl bg-white/2 light:bg-slate-900/[0.02] border border-white/5 light:border-slate-200">
                  <div className="min-w-0">
                    <p className="text-xs text-slate-300 light:text-slate-600 truncate">
                      {ACTION_LABELS[item.action] ?? item.action}
                    </p>
                    <p className="text-[10px] text-slate-500">{item.entity_type} · {new Date(item.created_at).toLocaleString("it-IT")}</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
