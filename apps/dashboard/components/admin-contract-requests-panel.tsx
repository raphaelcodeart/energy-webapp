"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CommissionPreviewView } from "@/components/contract-commission-preview";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { ContractDossierActions } from "@/components/contract-dossier-actions";
import { FullScreenPanel } from "@/components/full-screen-panel";
import { Pagination, usePagination } from "@/components/pagination";
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
import type {
  CommissionPreviewRead,
  ContractRead,
  ContractRequestDetailRead,
  ContractRequestPointRead,
  ContractRequestSummaryRead,
} from "@/lib/types";

type Filter = "ALL" | "TO_REVIEW" | "TO_PAY" | "DOCUMENTS" | "FAILED" | "DRAFT";

const FILTERS: { key: Filter; label: string; match: (r: ContractRequestSummaryRead) => boolean }[] = [
  { key: "TO_REVIEW", label: "Da verificare", match: (r) => r.points_to_review > 0 },
  { key: "DOCUMENTS", label: "Documenti mancanti", match: (r) => r.points_documents_pending > 0 },
  { key: "TO_PAY", label: "Non pagate", match: (r) => r.status === "SUBMITTED" && r.points_payable > 0 },
  { key: "FAILED", label: "Rate non riscosse", match: (r) => r.instalments_failed > 0 },
  { key: "DRAFT", label: "In compilazione", match: (r) => r.status === "DRAFT" },
  { key: "ALL", label: "Tutte", match: (r) => r.status !== "CANCELLED" },
];

const ORIGIN_LABELS: Record<string, string> = {
  CUSTOMER: "Dal cliente",
  PROMOTER: "Dal promoter",
  ADMIN: "Dall'amministrazione",
};

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** "Pratiche": every pratica di attivazione, for the back office (Session 52).
 *
 *  The list answers "what needs me?" -- pratiche with contracts to verify,
 *  missing documents, unpaid, failed instalments. The detail shows one
 *  pratica as the customer filled it in: the holder, the shared documents,
 *  every payment attempt, and each point as the independent contract it
 *  is. Approving, rejecting and the commission preview stay per contract --
 *  the same review modal as "Tutti i Contratti", opened from here -- with
 *  one addition: approving every contract waiting for review at once, each
 *  with its own preview accepted. */
export function AdminContractRequestsPanel({
  openRequestId,
  onOpenRequest,
  onReview,
  onCommissions,
  onHistory,
  onContractsChanged,
}: {
  openRequestId: string | null;
  onOpenRequest: (requestId: string | null) => void;
  onReview: (contract: ContractRead) => void;
  onCommissions: (contractId: string) => void;
  onHistory: (contractId: string) => void;
  /** "Tutti i Contratti" keeps its own copy of the list: told to reload it
      after contracts were approved from here. */
  onContractsChanged: () => void;
}) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["admin", "contract-requests"],
    queryFn: () => fetchJson<ContractRequestSummaryRead[]>("/api/proxy/contract-requests"),
    refetchOnWindowFocus: true,
  });
  const [filter, setFilter] = useState<Filter>("TO_REVIEW");
  const [search, setSearch] = useState("");

  const all = data ?? [];
  const needle = search.trim().toLowerCase();
  const active = FILTERS.find((f) => f.key === filter)!;
  const rows = all.filter(
    (r) =>
      active.match(r) &&
      (!needle ||
        [r.code, r.customer_name, r.holder_name, r.activated_by_promoter_name, r.id]
          .filter(Boolean)
          .some((v) => v!.toLowerCase().includes(needle)))
  );
  const pagination = usePagination(rows);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {FILTERS.filter((f) => f.key !== "ALL" && f.key !== "DRAFT").map((f) => {
          const count = all.filter(f.match).length;
          return (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`glass-card rounded-2xl p-4 text-left border transition cursor-pointer ${
                filter === f.key ? "border-orange-500/50 bg-orange-500/5" : "border-white/5 light:border-slate-200 bg-slate-950/20 light:bg-slate-50"
              }`}
            >
              <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">{f.label}</span>
              <span className={`text-2xl font-bold ${count > 0 && f.key !== "TO_PAY" ? "text-orange-400" : "text-white light:text-slate-900"}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between p-4 rounded-2xl bg-slate-900/40 light:bg-slate-50 border border-white/5 light:border-slate-200">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cerca per pratica, cliente, intestatario o promoter..."
          className="w-full sm:max-w-sm rounded-xl glass-input px-3 py-2 text-xs focus:border-orange-500"
        />
        <div className="flex gap-1.5 flex-wrap">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold transition cursor-pointer ${
                filter === f.key ? "bg-orange-600 text-white" : "bg-white/5 light:bg-slate-900/5 text-slate-400 light:text-slate-600 hover:bg-white/10"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-3 px-5">Pratica</th>
                <th className="py-3 px-5">Cliente</th>
                <th className="py-3 px-5">Punti</th>
                <th className="py-3 px-5 text-right">Totale</th>
                <th className="py-3 px-5">Pagamento</th>
                <th className="py-3 px-5 text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {isLoading && (
                <tr><td colSpan={6} className="py-8 text-center text-slate-500">Caricamento...</td></tr>
              )}
              {error && (
                <tr><td colSpan={6} className="py-8 text-center text-rose-400">{(error as Error).message}</td></tr>
              )}
              {pagination.pageItems.map((r) => (
                <tr key={r.id} className="text-slate-300 light:text-slate-600 hover:bg-white/5 cursor-pointer" onClick={() => onOpenRequest(r.id)}>
                  <td className="py-3 px-5">
                    <div className="text-sm font-semibold text-white light:text-slate-900">#{r.code}</div>
                    <div className="text-[10px] text-slate-500">
                      {r.status === "DRAFT" ? "Bozza · " : ""}
                      {formatDate(r.submitted_at ?? r.created_at)}
                    </div>
                  </td>
                  <td className="py-3 px-5">
                    <div className="text-sm font-semibold text-white light:text-slate-900">{r.customer_name ?? "—"}</div>
                    <div className="text-[10px] text-slate-500">
                      {ORIGIN_LABELS[r.created_by_role ?? ""] ?? "—"}
                      {r.activated_by_promoter_name ? ` · ${r.activated_by_promoter_name}` : ""}
                    </div>
                  </td>
                  <td className="py-3 px-5">
                    <div className="text-xs font-semibold text-white light:text-slate-900">
                      {r.points_active}/{r.points_total} attivi
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {[
                        r.points_to_review > 0 && `${r.points_to_review} da verificare`,
                        r.points_documents_pending > 0 && `${r.points_documents_pending} senza documenti`,
                        r.points_without_package > 0 && `${r.points_without_package} senza pacchetto`,
                      ].filter(Boolean).join(" · ") || "—"}
                    </div>
                  </td>
                  <td className="py-3 px-5 text-right text-sm font-semibold text-white light:text-slate-900 tabular-nums">
                    {r.total_gross_cents > 0 ? euro(r.total_gross_cents) : "—"}
                  </td>
                  <td className="py-3 px-5">
                    <div className="text-xs">
                      {r.points_paid > 0 ? `Pagati ${r.points_paid}/${r.points_total}` : r.status === "DRAFT" ? "—" : "Non pagata"}
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {r.payment_plans.map((p) => PAYMENT_PLAN_LABELS[p] ?? p).join(", ")}
                      {r.instalments_failed > 0 && <span className="text-rose-400"> · {r.instalments_failed} rate non riscosse</span>}
                    </div>
                  </td>
                  <td className="py-3 px-5 text-right">
                    <span className="px-3 py-1 rounded-lg bg-orange-600/10 border border-orange-500/20 text-orange-400 text-xs font-semibold">
                      Apri
                    </span>
                  </td>
                </tr>
              ))}
              {!isLoading && !error && rows.length === 0 && (
                <tr><td colSpan={6} className="py-8 text-center text-slate-500">Nessuna pratica in “{active.label}”.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="px-5 pb-4">
          <Pagination {...pagination} label="pratiche" />
        </div>
      </div>

      {openRequestId && (
        <RequestDetail
          requestId={openRequestId}
          onClose={() => onOpenRequest(null)}
          onReview={onReview}
          onCommissions={onCommissions}
          onHistory={onHistory}
          onContractsChanged={onContractsChanged}
        />
      )}
    </div>
  );
}

function RequestDetail({
  requestId,
  onClose,
  onReview,
  onCommissions,
  onHistory,
  onContractsChanged,
}: {
  requestId: string;
  onClose: () => void;
  onReview: (contract: ContractRead) => void;
  onCommissions: (contractId: string) => void;
  onHistory: (contractId: string) => void;
  onContractsChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: request, error } = useQuery({
    queryKey: ["contract-request", requestId],
    queryFn: () => fetchJson<ContractRequestDetailRead>(`/api/proxy/contract-requests/${requestId}`),
    refetchOnWindowFocus: true,
  });
  const [openPoint, setOpenPoint] = useState<string | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [stopping, setStopping] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["contract-request", requestId] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "contract-requests"] }),
    ]);
  }

  async function stopBilling(point: ContractRequestPointRead) {
    if (
      !window.confirm(
        `Interrompere gli addebiti mensili di ${pointCode(point)}? Gli altri contratti della pratica continuano a essere addebitati. Eventuali rimborsi si fanno dal pannello Stripe.`
      )
    ) {
      return;
    }
    setStopping(point.id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${point.id}/stop-billing`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
    } catch (err: any) {
      setActionError(err.message || "Impossibile interrompere gli addebiti.");
    } finally {
      setStopping(null);
    }
  }

  const toReview = (request?.points ?? []).filter((p) => p.status === "UNDER_REVIEW");

  return (
    <FullScreenPanel
      eyebrow="Pratica di attivazione"
      title={request ? `#${request.code} · ${request.customer_name ?? "Cliente"}` : "Pratica"}
      onClose={onClose}
      subtitle={
        request && (
          <p className="text-[11px] text-slate-400 light:text-slate-500">
            {ORIGIN_LABELS[request.created_by_role ?? ""] ?? "—"}
            {request.activated_by_promoter_name ? ` (${request.activated_by_promoter_name})` : ""} ·{" "}
            {request.status === "DRAFT" ? "in compilazione" : `inviata il ${formatDate(request.submitted_at)}`} ·{" "}
            {request.points_total} punti · {request.points_active} attivi · totale{" "}
            <strong className="text-orange-400">{euro(request.total_gross_cents)}</strong>
          </p>
        )
      }
    >
      {error && <p className="text-sm text-rose-400">{(error as Error).message}</p>}
      {!request ? (
        <div className="h-40 rounded-2xl bg-white/5 light:bg-slate-900/5 animate-pulse" />
      ) : (
        <div className="space-y-6">
          {actionError && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{actionError}</div>
          )}

          <section className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 rounded-2xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200 text-xs">
            <Fact label="Intestatario" value={request.holder_name ?? "—"} />
            <Fact label="Email" value={request.email ?? "—"} />
            <Fact label="PEC" value={request.pec ?? "—"} />
            <Fact label="IBAN" value={request.iban ?? "—"} mono />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <h3 className="text-sm font-bold text-white light:text-slate-900">Contratti della pratica</h3>
              {toReview.length > 0 && (
                <button
                  onClick={() => setBulkOpen(true)}
                  className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white transition cursor-pointer"
                >
                  Approva {toReview.length === 1 ? "il contratto in revisione" : `i ${toReview.length} contratti in revisione`}
                </button>
              )}
            </div>
            <div className="space-y-2">
              {request.points.map((point) => (
                <div key={point.id} className="rounded-2xl border border-white/10 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
                  <div className="p-3.5 flex flex-col lg:flex-row lg:items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
                        {ENERGY_POINT_LABELS[point.energy_type ?? ""] ?? "Fornitura"} · contratto {point.id.slice(0, 8).toUpperCase()}
                      </p>
                      <p className="text-sm font-bold text-white light:text-slate-900 font-mono">{pointCode(point)}</p>
                      <p className="text-[11px] text-slate-400 light:text-slate-500 truncate">
                        {[point.street, point.postal_code, point.city, point.province].filter(Boolean).join(", ")}
                        {point.meter_number ? ` · contatore ${point.meter_number}` : ""}
                      </p>
                    </div>
                    <div className="min-w-0 lg:w-48">
                      <p className="text-xs font-semibold text-white light:text-slate-900 truncate">{point.product_name ?? "Senza pacchetto"}</p>
                      <p className="text-[11px] text-slate-400 light:text-slate-500 tabular-nums">
                        {point.gross_amount_cents != null ? euro(point.gross_amount_cents) : "—"}
                        {point.vat_amount_cents ? ` (IVA ${point.vat_rate}%)` : ""}
                      </p>
                    </div>
                    <div className="lg:w-44 space-y-1">
                      <button
                        onClick={() => onHistory(point.id)}
                        title="Storico stati"
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold border cursor-pointer ${contractStatusBadge(point.status)}`}
                      >
                        {CONTRACT_STATUS_LABELS[point.status] ?? point.status}
                      </button>
                      <p className="text-[10px] text-slate-500">
                        {point.paid_at ? (
                          <span className="text-emerald-400">
                            Pagato{point.payment_plan ? ` · ${PAYMENT_PLAN_LABELS[point.payment_plan] ?? point.payment_plan}` : ""}
                          </span>
                        ) : (
                          "Non pagato"
                        )}
                        {point.instalments_total && point.instalments_total > 1
                          ? ` · rate ${point.instalments_paid}/${point.instalments_total}`
                          : ""}
                        {point.instalments_failed > 0 && <span className="text-rose-400"> · {point.instalments_failed} non riscosse</span>}
                        {point.billing_stopped_at && <span className="text-rose-400"> · addebiti interrotti</span>}
                      </p>
                      <p className={`text-[10px] ${point.documents_missing > 0 || point.documents_rejected > 0 ? "text-amber-400" : "text-slate-500"}`}>
                        {point.documents_missing > 0
                          ? `${point.documents_missing} documenti mancanti`
                          : point.documents_rejected > 0
                            ? `${point.documents_rejected} documenti respinti`
                            : "Documenti completi"}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 lg:justify-end">
                      <button
                        onClick={() => setOpenPoint(openPoint === point.id ? null : point.id)}
                        className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-[11px] font-semibold cursor-pointer"
                      >
                        {openPoint === point.id ? "Chiudi" : "Documenti"}
                      </button>
                      {point.product_version_id && (
                        <button
                          onClick={() => onCommissions(point.id)}
                          className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-[11px] font-semibold cursor-pointer"
                        >
                          Provvigioni
                        </button>
                      )}
                      {point.status !== "DRAFT" && (
                        <button
                          onClick={() => onReview(point)}
                          className="px-2.5 py-1 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-[11px] font-semibold cursor-pointer"
                        >
                          Recensisci
                        </button>
                      )}
                      {point.billing_active && (
                        <button
                          onClick={() => stopBilling(point)}
                          disabled={stopping === point.id}
                          className="px-2.5 py-1 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-[11px] font-semibold cursor-pointer disabled:opacity-50"
                        >
                          {stopping === point.id ? "..." : "Interrompi addebiti"}
                        </button>
                      )}
                    </div>
                  </div>
                  {openPoint === point.id && (
                    <div className="border-t border-white/5 light:border-slate-200 p-4 space-y-4">
                      <ContractDocumentsPanel contractId={point.id} isStaff />
                      <ContractDossierActions contractId={point.id} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-bold text-white light:text-slate-900">Documenti dell&apos;intestatario</h3>
            <p className="text-xs text-slate-400 light:text-slate-500">
              Caricati una volta sulla pratica: valgono per ogni contratto qui sopra, e compaiono anche nel fascicolo di
              ciascuno.
            </p>
            <ContractDocumentsPanel requestId={request.id} isStaff />
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-bold text-white light:text-slate-900">Tentativi di pagamento</h3>
            {request.checkouts.length === 0 ? (
              <p className="text-xs text-slate-500">
                Nessun pagamento con carta avviato per questa pratica
                {request.points_paid > 0 ? " (i contratti pagati lo sono stati singolarmente o con bonifico confermato)." : "."}
              </p>
            ) : (
              <div className="rounded-2xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200 text-xs">
                {request.checkouts.map((c) => (
                  <div key={c.id} className="px-4 py-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold text-white light:text-slate-900">
                        {PAYMENT_PLAN_LABELS[c.payment_plan] ?? c.payment_plan} · {c.contracts} contratti ·{" "}
                        {c.payment_plan === "FULL" ? euro(c.total_cents) : `${euro(c.instalment_cents)}/mese (${euro(c.total_cents)})`}
                      </p>
                      <p className="text-[10px] text-slate-500 font-mono">
                        {c.stripe_checkout_session_id}
                        {c.stripe_subscription_id ? ` · ${c.stripe_subscription_id}` : ""}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className={c.completed_at ? "text-emerald-400 font-semibold" : "text-slate-500"}>
                        {c.completed_at ? `Completato il ${formatDate(c.completed_at)}` : `Aperto il ${formatDate(c.created_at)}, non completato`}
                      </p>
                      {c.outcome && <p className="text-[10px] text-slate-500">{c.outcome}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {bulkOpen && request && (
        <BulkApproveModal
          points={toReview}
          onClose={() => setBulkOpen(false)}
          onDone={async () => {
            await refresh();
            onContractsChanged();
          }}
        />
      )}
    </FullScreenPanel>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</p>
      <p className={`text-slate-200 light:text-slate-800 font-semibold truncate ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

type BulkResult = { contractId: string; ok: boolean; message: string };

/** Approving every contract waiting for review, in one go -- without
    skipping what makes approval safe. Each contract's commission preview is
    loaded and shown; the administrator accepts them all with one tick, and
    each transition is still sent on its own with its own checksum, so a
    preview that changed in the meantime is refused for that contract alone
    and the others go through. */
function BulkApproveModal({
  points,
  onClose,
  onDone,
}: {
  points: ContractRequestPointRead[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("Documenti verificati");
  const [checked, setChecked] = useState(false);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<BulkResult[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: previews, error } = useQuery({
    queryKey: ["admin", "bulk-previews", points.map((p) => p.id).join(",")],
    queryFn: async () => {
      const out: Record<string, CommissionPreviewRead> = {};
      for (const point of points) {
        out[point.id] = await fetchJson<CommissionPreviewRead>(`/api/proxy/contracts/${point.id}/commission-preview`);
      }
      return out;
    },
    staleTime: 0,
    gcTime: 0,
  });

  async function approveAll() {
    if (!previews) return;
    setRunning(true);
    const out: BulkResult[] = [];
    for (const point of points) {
      const preview = previews[point.id];
      if (!preview) continue;
      try {
        const res = await fetch(`/api/proxy/contracts/${point.id}/transition`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            to_status: "APPROVED",
            reason,
            notes: null,
            accept_commission_preview_checksum: preview.already_accepted ? null : preview.checksum,
          }),
        });
        if (!res.ok) throw new Error(await friendlyApiError(res));
        const updated = (await res.json()) as ContractRead;
        out.push({
          contractId: point.id,
          ok: true,
          message: `${pointCode(point)}: ${CONTRACT_STATUS_LABELS[updated.status] ?? updated.status}`,
        });
      } catch (err: any) {
        out.push({ contractId: point.id, ok: false, message: `${pointCode(point)}: ${err.message}` });
      }
    }
    setResults(out);
    setRunning(false);
    onDone();
  }

  const total = previews ? Object.values(previews).reduce((sum, p) => sum + p.total_commission_cents, 0) : 0;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm">
      <div className="w-full max-w-3xl max-h-[88vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-white light:text-slate-900">
            Approva {points.length} {points.length === 1 ? "contratto" : "contratti"}
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/5 text-slate-400 cursor-pointer">✕</button>
        </div>

        {results ? (
          <>
            <div className="space-y-1.5">
              {results.map((r) => (
                <p key={r.contractId} className={`text-xs ${r.ok ? "text-emerald-400" : "text-rose-400"}`}>
                  {r.ok ? "✓" : "✕"} {r.message}
                </p>
              ))}
            </div>
            <button onClick={onClose} className="w-full rounded-xl bg-white/10 hover:bg-white/20 py-2.5 text-sm font-semibold text-white light:text-slate-700 cursor-pointer">
              Chiudi
            </button>
          </>
        ) : (
          <>
            <p className="text-xs text-slate-400 light:text-slate-500">
              Approvare un contratto fa partire le sue provvigioni (subito se già pagato, a ogni rata se a rate). Controlla le
              anteprime: ognuna viene accettata e salvata nel registro del suo contratto.
            </p>
            {error && <p className="text-xs text-rose-400">{(error as Error).message}</p>}
            {!previews ? (
              <div className="h-32 rounded-xl bg-white/5 light:bg-slate-900/5 animate-pulse" />
            ) : (
              <div className="space-y-2">
                {points.map((point) => {
                  const preview = previews[point.id];
                  if (!preview) return null;
                  return (
                    <div key={point.id} className="rounded-xl border border-white/10 light:border-slate-200">
                      <button
                        onClick={() => setExpanded(expanded === point.id ? null : point.id)}
                        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left cursor-pointer"
                      >
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-white light:text-slate-900 font-mono">{pointCode(point)}</span>
                          <span className="block text-[11px] text-slate-400">
                            {point.product_name} · {preview.beneficiaries.filter((b) => b.total_cents > 0).length} beneficiari
                            {preview.warnings.length > 0 && <span className="text-amber-400"> · {preview.warnings.length} avvisi</span>}
                            {preview.already_accepted && " · anteprima già accettata"}
                          </span>
                        </span>
                        <span className="text-sm font-bold text-orange-400 tabular-nums shrink-0">
                          {euro(preview.total_commission_cents)} {expanded === point.id ? "▾" : "▸"}
                        </span>
                      </button>
                      {expanded === point.id && (
                        <div className="border-t border-white/5 light:border-slate-200 p-4">
                          <CommissionPreviewView preview={preview} />
                        </div>
                      )}
                    </div>
                  );
                })}
                <p className="text-xs text-slate-300 light:text-slate-700 text-right">
                  Provvigioni totali: <strong className="text-orange-400">{euro(total)}</strong>
                </p>
              </div>
            )}
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 block">Motivazione</label>
              <input
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              />
            </div>
            <label className="flex items-start gap-2 cursor-pointer">
              <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} className="mt-0.5 accent-orange-500" />
              <span className="text-xs text-slate-300 light:text-slate-700">
                Ho verificato i documenti e controllato le anteprime: accetto che le provvigioni di ogni contratto partano
                come indicato.
              </span>
            </label>
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 cursor-pointer">
                Annulla
              </button>
              <button
                onClick={approveAll}
                disabled={!previews || !checked || !reason.trim() || running}
                className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
              >
                {running ? "Approvazione in corso..." : `Accetta e approva ${points.length}`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
