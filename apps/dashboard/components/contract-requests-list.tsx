"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { friendlyApiError } from "@/lib/api-error";
import {
  CONTRACT_STATUS_LABELS,
  ENERGY_POINT_LABELS,
  PAYMENT_PLAN_LABELS,
  contractStatusBadge,
  formatDate,
  pointCode,
} from "@/lib/contract-status";
import { formatEuroCents as euro } from "@/lib/product-audience";
import type { ContractRequestDetailRead, ContractRequestPointRead, ContractRequestSummaryRead } from "@/lib/types";

export type WizardTarget = { requestId: string; step?: "documents" | "packages" | "summary" };

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** What a pratica is waiting for, in one sentence -- the first thing the
    customer (or their promoter) reads on the card. */
function nextStepFor(r: ContractRequestSummaryRead, canPay: boolean): { text: string; tone: "action" | "wait" | "done" } {
  if (r.status === "DRAFT") {
    return {
      text: r.points_total === 0
        ? "Bozza: completa i dati."
        : r.points_without_package > 0
          ? `Bozza: scegli il contratto per ${r.points_without_package} POD e invia.`
          : "Bozza: pronta da inviare.",
      tone: "action",
    };
  }
  if (r.instalments_failed > 0) return { text: "Una rata non è stata addebitata: controlla la carta.", tone: "action" };
  if (r.points_payable > 0) {
    return {
      text: canPay
        ? `Da pagare: ${r.points_payable} ${r.points_payable === 1 ? "contratto" : "contratti"}.`
        : `In attesa del pagamento del cliente (${r.points_payable} ${r.points_payable === 1 ? "contratto" : "contratti"}).`,
      tone: "action",
    };
  }
  if (r.points_documents_pending > 0) {
    return {
      text: `Mancano documenti per ${r.points_documents_pending} POD.`,
      tone: "action",
    };
  }
  if (r.points_active === r.points_total && r.points_total > 0) return { text: "Tutti i contratti sono attivi.", tone: "done" };
  if (r.points_to_review > 0) return { text: "Documenti in verifica dall'amministrazione.", tone: "wait" };
  return { text: "In lavorazione.", tone: "wait" };
}

/** "I miei Contratti" as a list of pratiche (Session 52): each one opens on
    its supply points, each point a contract of its own with its status,
    package and documents.

    `mode="customer"` lists the logged-in customer's own; `mode="promoter"`
    one customer of the promoter's (`customerId`), with everything except
    the payment. */
export function ContractRequestsList({
  mode,
  customerId,
  onOpenWizard,
}: {
  mode: "customer" | "promoter";
  customerId?: string;
  onOpenWizard: (target: WizardTarget) => void;
}) {
  const path = mode === "customer" ? "/api/proxy/contract-requests/mine" : `/api/proxy/contract-requests/for-customer/${customerId}`;
  const { data, error, isLoading } = useQuery({
    queryKey: ["contract-requests", mode, customerId ?? "mine"],
    queryFn: () => fetchJson<ContractRequestSummaryRead[]>(path),
    refetchOnWindowFocus: true,
  });
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading) return <div className="h-28 rounded-2xl bg-white/5 light:bg-slate-900/5 animate-pulse" />;
  if (error) return <p className="text-sm text-rose-400">{(error as Error).message}</p>;
  if (!data || data.length === 0) {
    return (
      <div className="glass-card rounded-2xl p-8 text-center border-white/5 light:border-slate-200">
        <p className="text-sm font-semibold text-white light:text-slate-900">Nessuna pratica</p>
        <p className="text-xs text-slate-500 mt-1">
          {mode === "customer"
            ? "Attiva il tuo primo contratto: puoi inserire uno o più punti di fornitura insieme."
            : "Questo cliente non ha ancora nessuna pratica di attivazione."}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {data.map((r) => {
        const next = nextStepFor(r, mode === "customer");
        const isOpen = expanded === r.id;
        return (
          <div key={r.id} className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
            <div className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
              <button onClick={() => setExpanded(isOpen ? null : r.id)} className="text-left min-w-0 flex-1 cursor-pointer">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-bold text-white light:text-slate-900">Pratica #{r.code}</span>
                  {r.status === "DRAFT" && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-slate-500/10 text-slate-400 border-slate-500/20">
                      Bozza
                    </span>
                  )}
                  {r.activated_by_promoter_name && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-sky-500/10 text-sky-400 border-sky-500/20">
                      {mode === "customer" ? `Preparata dal tuo promoter ${r.activated_by_promoter_name}` : `Compilata da ${r.activated_by_promoter_name}`}
                    </span>
                  )}
                  <span className="text-[11px] text-slate-500">
                    {formatDate(r.submitted_at ?? r.created_at)} · {r.points_total} POD
                    {r.payment_plans.length > 0 && ` · ${r.payment_plans.map((p) => PAYMENT_PLAN_LABELS[p] ?? p).join(", ")}`}
                  </span>
                </div>
                <p
                  className={`text-xs mt-1 ${
                    next.tone === "action" ? "text-amber-400" : next.tone === "done" ? "text-emerald-400" : "text-slate-400 light:text-slate-500"
                  }`}
                >
                  {next.text}
                </p>
                {r.status !== "DRAFT" && r.points_total > 0 && (
                  <div className="mt-2 flex items-center gap-2">
                    <div className="h-1.5 flex-1 max-w-48 rounded-full bg-white/10 light:bg-slate-200 overflow-hidden">
                      <div className="h-full bg-emerald-500" style={{ width: `${(r.points_active / r.points_total) * 100}%` }} />
                    </div>
                    <span className="text-[10px] text-slate-500 tabular-nums">
                      {r.points_active}/{r.points_total} attivi
                    </span>
                  </div>
                )}
              </button>
              <div className="flex items-center gap-2 shrink-0">
                {r.total_gross_cents > 0 && (
                  <span className="text-sm font-bold text-white light:text-slate-900 tabular-nums mr-1">{euro(r.total_gross_cents)}</span>
                )}
                {r.status === "DRAFT" ? (
                  <button
                    onClick={() => onOpenWizard({ requestId: r.id })}
                    className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-bold text-white transition cursor-pointer"
                  >
                    Riprendi
                  </button>
                ) : mode === "customer" && r.points_payable > 0 ? (
                  <button
                    onClick={() => onOpenWizard({ requestId: r.id, step: "summary" })}
                    className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-bold text-white transition cursor-pointer"
                  >
                    Paga
                  </button>
                ) : (
                  <button
                    onClick={() => setExpanded(isOpen ? null : r.id)}
                    className="px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-300 light:text-slate-600 transition cursor-pointer"
                  >
                    {isOpen ? "Chiudi" : "Dettagli"}
                  </button>
                )}
              </div>
            </div>
            {isOpen && <RequestPoints requestId={r.id} mode={mode} onOpenWizard={onOpenWizard} />}
          </div>
        );
      })}
    </div>
  );
}

function RequestPoints({
  requestId,
  mode,
  onOpenWizard,
}: {
  requestId: string;
  mode: "customer" | "promoter";
  onOpenWizard: (target: WizardTarget) => void;
}) {
  const { data, error } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchJson<ContractRequestDetailRead>(`/api/proxy/contract-requests/${requestId}`),
  });
  const [openPoint, setOpenPoint] = useState<string | null>(null);

  if (error) return <p className="px-5 pb-4 text-sm text-rose-400">{(error as Error).message}</p>;
  if (!data) return <div className="mx-5 mb-4 h-20 rounded-xl bg-white/5 light:bg-slate-900/5 animate-pulse" />;

  return (
    <div className="border-t border-white/5 light:border-slate-200 px-4 sm:px-5 py-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400 light:text-slate-500">
        <span>
          Intestatario: <strong className="text-slate-300 light:text-slate-700">{data.holder_name ?? "—"}</strong>
          {data.email ? ` · ${data.email}` : ""}
          {data.activated_by_promoter_name ? ` · compilata da ${data.activated_by_promoter_name}` : ""}
        </span>
        {data.status !== "DRAFT" && (
          <button
            onClick={() => onOpenWizard({ requestId, step: "documents" })}
            className="font-semibold text-orange-400 hover:text-orange-300 cursor-pointer"
          >
            Documenti d&apos;identità →
          </button>
        )}
      </div>

      {data.points.map((point) => (
        <PointRow
          key={point.id}
          point={point}
          open={openPoint === point.id}
          onToggle={() => setOpenPoint(openPoint === point.id ? null : point.id)}
          mode={mode}
        />
      ))}
    </div>
  );
}

function PointRow({
  point,
  open,
  onToggle,
  mode,
}: {
  point: ContractRequestPointRead;
  open: boolean;
  onToggle: () => void;
  mode: "customer" | "promoter";
}) {
  return (
    <div className="rounded-xl border border-white/10 light:border-slate-200 bg-white/[0.03] light:bg-white">
      <button onClick={onToggle} className="w-full flex items-center justify-between gap-3 p-3 text-left cursor-pointer">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
            {ENERGY_POINT_LABELS[point.energy_type ?? ""] ?? "Fornitura"} · {point.product_name ?? "Contratto da scegliere"}
          </p>
          <p className="text-sm font-semibold text-white light:text-slate-900 font-mono truncate">{pointCode(point)}</p>
          <p className="text-[11px] text-slate-400 light:text-slate-500 truncate">
            {[point.street, point.city].filter(Boolean).join(", ")}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${contractStatusBadge(point.status)}`}>
            {CONTRACT_STATUS_LABELS[point.status] ?? point.status}
          </span>
          <span className="text-[10px] text-slate-500">
            {point.paid_at ? "Pagato" : point.gross_amount_cents != null ? euro(point.gross_amount_cents) : ""}
            {point.instalments_total && point.instalments_total > 1 ? ` · rate ${point.instalments_paid}/${point.instalments_total}` : ""}
          </span>
        </div>
      </button>
      {open && (
        <div className="border-t border-white/5 light:border-slate-200 p-3 space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px]">
            <Fact label="Contratto" value={point.id.slice(0, 8).toUpperCase()} mono />
            <Fact label="Attivo dal" value={formatDate(point.activated_at)} />
            <Fact label="Scadenza" value={formatDate(point.expires_at)} />
            <Fact label="Contatore" value={point.meter_number ?? "—"} />
          </div>
          {point.status === "REJECTED" && (
            <p className="text-xs text-rose-400">
              Questo contratto non è stato approvato. Gli altri punti della pratica non ne risentono. Contatta il supporto per
              i dettagli.
            </p>
          )}
          {point.documents_missing > 0 && (
            <p className="text-xs text-amber-400">
              {mode === "customer" ? "Carica" : "Manca"} la bolletta di questo punto (oppure un&apos;unica bolletta sulla pratica).
            </p>
          )}
          {mode === "customer" && <IbanEditor contractId={point.id} initialIban={point.iban} />}
          <ContractDocumentsPanel contractId={point.id} />
        </div>
      )}
    </div>
  );
}

/** The IBAN of one contract, correctable after the pratica was sent -- a
    customer may change bank, or have typed it wrong. */
function IbanEditor({ contractId, initialIban }: { contractId: string; initialIban: string | null }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(initialIban ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/iban`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ iban: value.replace(/\s/g, "").toUpperCase() }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditing(false);
      await queryClient.invalidateQueries({ queryKey: ["contract-request"] });
    } catch (err: any) {
      setError(err.message || "IBAN non valido. Controlla il formato inserito.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="text-[11px]">
      <span className="text-slate-500">IBAN per addebito</span>
      {editing ? (
        <div className="flex items-center gap-2 mt-0.5">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="IT00A0000000000000000000000"
            className="w-full max-w-xs rounded-lg glass-input px-2 py-1 text-xs uppercase font-mono focus:border-orange-500"
          />
          <button onClick={handleSave} disabled={saving} className="font-semibold text-emerald-400 cursor-pointer disabled:opacity-50">
            {saving ? "..." : "Salva"}
          </button>
          <button onClick={() => setEditing(false)} className="font-semibold text-slate-500 cursor-pointer">
            Annulla
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 mt-0.5">
          <span className="font-mono text-slate-300 light:text-slate-600">{initialIban ?? "Non impostato"}</span>
          <button onClick={() => { setValue(initialIban ?? ""); setEditing(true); }} className="font-semibold text-orange-400 cursor-pointer">
            {initialIban ? "Modifica" : "Aggiungi"}
          </button>
        </div>
      )}
      {error && <p className="text-rose-400 mt-1">{error}</p>}
    </div>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-slate-500">{label}</p>
      <p className={`text-slate-300 light:text-slate-700 font-semibold ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

/** For the few places that just need to refresh every pratiche list. */
export function useInvalidateContractRequests() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["contract-requests"] });
    queryClient.invalidateQueries({ queryKey: ["contract-request"] });
  };
}
