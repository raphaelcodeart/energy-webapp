"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { formatEuroCents as euro } from "@/lib/product-audience";
import type { CommissionPreviewRead, ContractCommissionLogRead } from "@/lib/types";

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("it-IT") : "—";
}

const SOURCE_LABELS: Record<string, string> = {
  STRIPE_CHECKOUT: "Stripe (primo pagamento)",
  STRIPE_INVOICE: "Stripe (rata mensile)",
  ADMIN: "Confermata a mano",
};

/** The commission preview, as the administrator reads it before approving.
 *
 *  Every figure comes from the server (commissions/services/preview.py): who
 *  is above the customer, what each of them earns, and how that is spread
 *  over the customer's payments. This component only lays it out -- the
 *  same rendering is reused, read-only, in the log afterwards. */
export function CommissionPreviewView({ preview }: { preview: CommissionPreviewRead }) {
  const { payment } = preview;
  const payees = preview.beneficiaries.filter((b) => b.total_cents > 0).length + (preview.first_referrer_bonus ? 1 : 0);
  const split = payment.paid && (payment.instalments ?? 1) > 1;
  const firstRow = payment.schedule[0];

  return (
    <div className="space-y-4">
      <div className="p-4 rounded-xl bg-orange-500/10 border border-orange-500/20">
        <p className="text-sm text-white light:text-slate-900">
          Provvigioni totali su questo contratto:{" "}
          <strong className="text-orange-400 tabular-nums">{euro(preview.total_commission_cents)}</strong>
          {" "}a {payees} promoter
        </p>
        <p className="text-xs text-slate-400 light:text-slate-600 mt-1">
          {!payment.paid
            ? "Il cliente non ha ancora pagato: le provvigioni partiranno da sole al primo pagamento, divise come mostrato sotto."
            : split
              ? `Pagamento in ${payment.instalments} rate: all'approvazione parte la quota della 1ª rata (${euro(firstRow?.commission_cents ?? 0)}); le altre partono a ogni rata incassata, fino al ${formatDate(payment.last_release_date)}.`
              : "Pagamento unico: all'approvazione partono tutte le provvigioni, una volta sola."}
        </p>
      </div>

      {preview.warnings.length > 0 && (
        <ul className="space-y-1.5">
          {preview.warnings.map((w) => (
            <li key={w} className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">{w}</li>
          ))}
        </ul>
      )}

      <div>
        <p className="text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase mb-2">
          Chi riceve cosa — dal promoter del cliente verso l&apos;alto
        </p>
        <div className="space-y-1.5">
          {preview.beneficiaries.map((b) => (
            <div
              key={b.agent_id}
              className={`flex items-center justify-between gap-3 p-3 rounded-xl border ${
                b.total_cents > 0
                  ? "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-200"
                  : "border-dashed border-white/10 light:border-slate-200 opacity-60"
              }`}
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-white light:text-slate-900 truncate">{b.name}</p>
                <p className="text-[11px] text-slate-400 light:text-slate-500">
                  {b.role} · grado <span className="text-orange-400 font-semibold">{b.rank_code}</span> · {b.movement_label}
                </p>
                <p className="text-[10px] text-slate-500 mt-0.5">{b.explanation}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-base font-bold text-orange-400 tabular-nums">{euro(b.total_cents)}</p>
                {split && b.total_cents > 0 && firstRow && (
                  <p className="text-[10px] text-slate-500">
                    {euro(firstRow.per_beneficiary_cents[b.agent_id] ?? 0)} a rata × {payment.instalments}
                  </p>
                )}
              </div>
            </div>
          ))}
          {preview.first_referrer_bonus && (
            <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
              <div>
                <p className="text-sm font-semibold text-white light:text-slate-900">{preview.first_referrer_bonus.name}</p>
                <p className="text-[11px] text-slate-400 light:text-slate-500">
                  Bonus primo segnalatore · {preview.first_referrer_bonus.note}
                </p>
              </div>
              <p className="text-base font-bold text-orange-400 tabular-nums">{euro(preview.first_referrer_bonus.amount_cents)}</p>
            </div>
          )}
          {preview.beneficiaries.length === 0 && (
            <p className="text-xs text-slate-500">Nessun promoter nella catena.</p>
          )}
        </div>
      </div>

      <div>
        <p className="text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase mb-2">
          Come partono le provvigioni
        </p>
        {payment.paid ? (
          <div className="overflow-x-auto rounded-xl border border-white/5 light:border-slate-200">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="text-slate-400 light:text-slate-500 border-b border-white/5 light:border-slate-200">
                  <th className="py-2 px-3">Rata</th>
                  <th className="py-2 px-3">Data prevista</th>
                  <th className="py-2 px-3 text-right">Incasso cliente</th>
                  <th className="py-2 px-3 text-right">Provvigioni</th>
                  <th className="py-2 px-3">Quando partono</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 light:divide-slate-200 text-slate-300 light:text-slate-600">
                {payment.schedule.map((row) => (
                  <tr key={row.number}>
                    <td className="py-2 px-3 font-semibold">{row.number} di {payment.instalments}</td>
                    <td className="py-2 px-3">{formatDate(row.due_date)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{euro(row.customer_amount_cents)}</td>
                    <td className="py-2 px-3 text-right tabular-nums font-semibold text-orange-400">{euro(row.commission_cents)}</td>
                    <td className="py-2 px-3 text-[11px]">{row.release}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {payment.scenarios.map((s) => (
              <div key={s.plan_key} className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
                <p className="text-xs font-semibold text-white light:text-slate-900">Se paga: {s.plan_label.toLowerCase()}</p>
                <p className="text-sm font-bold text-orange-400 tabular-nums mt-1">{euro(s.commission_per_instalment_cents)}</p>
                <p className="text-[10px] text-slate-500">
                  {s.instalments === 1 ? "tutte subito, una volta" : `a ogni rata incassata, per ${s.instalments} mesi`}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {preview.customer_cashback_cents > 0 && (
        <p className="text-[11px] text-slate-400 light:text-slate-500">
          Il cliente riceve inoltre{" "}
          <strong className="text-emerald-400 tabular-nums">
            {(preview.customer_cashback_cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2 })} LialCash
          </strong>{" "}
          di cashback sul proprio wallet, man mano che paga. Non è una provvigione e non va ai promoter.
        </p>
      )}
    </div>
  );
}

async function fetchLog(contractId: string): Promise<ContractCommissionLogRead> {
  const res = await fetch(`/api/proxy/contracts/${contractId}/commission-log`);
  if (!res.ok) throw new Error("Impossibile caricare il registro provvigioni.");
  return res.json();
}

/** "Registro provvigioni" of one contract: the preview the administrator
 *  accepted (who, when, exactly what they saw), and the instalment schedule
 *  with what each payment has released so far. An instalment Stripe did not
 *  collect can be confirmed here by hand. */
export function ContractCommissionLog({ contractId }: { contractId: string }) {
  const queryClient = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["admin", "commission-log", contractId], queryFn: () => fetchLog(contractId) });
  const [showPreview, setShowPreview] = useState(false);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  async function handleConfirm(number: number) {
    if (!window.confirm(
      `Confermi di aver ricevuto la rata ${number}? Se il contratto è attivo partono subito le provvigioni di questa rata. ` +
      "Usalo solo se Stripe non l'ha incassata (es. il cliente ha pagato con bonifico)."
    )) return;
    setConfirming(number);
    setConfirmError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/instalments/${number}/confirm`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "commission-log", contractId] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "commissions"] });
    } catch (err: any) {
      setConfirmError(err.message || "Impossibile confermare la rata.");
    } finally {
      setConfirming(null);
    }
  }

  if (error) return <p className="text-sm text-rose-400">Impossibile caricare il registro provvigioni.</p>;
  if (!data) return <div className="h-20 rounded-xl bg-white/5 light:bg-slate-900/5 animate-pulse" />;

  return (
    <div className="space-y-4">
      {data.accepted_plan ? (
        <div className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-xs text-slate-300 light:text-slate-600">
              Anteprima accettata il <strong>{new Date(data.accepted_plan.accepted_at).toLocaleString("it-IT")}</strong>
              {data.accepted_plan.accepted_by && <> da <strong>{data.accepted_plan.accepted_by}</strong></>} · totale{" "}
              <strong className="text-orange-400">{euro(data.accepted_plan.total_commission_cents)}</strong>
            </p>
            <button
              onClick={() => setShowPreview((v) => !v)}
              className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-[11px] font-semibold text-slate-300 light:text-slate-600 transition cursor-pointer"
            >
              {showPreview ? "Nascondi anteprima" : "Apri l'anteprima accettata"}
            </button>
          </div>
          {showPreview && (
            <div className="mt-4">
              <CommissionPreviewView preview={data.accepted_plan.preview} />
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-slate-500">
          Nessuna anteprima accettata: il contratto è stato approvato prima di questa funzione, oppure non è ancora approvato.
        </p>
      )}

      {data.instalments.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase mb-2">Rate e provvigioni rilasciate</p>
          {confirmError && (
            <div className="p-2.5 mb-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{confirmError}</div>
          )}
          <div className="overflow-x-auto rounded-xl border border-white/5 light:border-slate-200">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="text-slate-400 light:text-slate-500 border-b border-white/5 light:border-slate-200">
                  <th className="py-2 px-3">Rata</th>
                  <th className="py-2 px-3">Prevista</th>
                  <th className="py-2 px-3 text-right">Importo</th>
                  <th className="py-2 px-3">Pagamento</th>
                  <th className="py-2 px-3">Provvigioni</th>
                  <th className="py-2 px-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 light:divide-slate-200 text-slate-300 light:text-slate-600">
                {data.instalments.map((r) => (
                  <tr key={r.number}>
                    <td className="py-2 px-3 font-semibold">{r.number} di {r.instalments_total}</td>
                    <td className="py-2 px-3">{formatDate(r.due_date)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{euro(r.amount_cents)}</td>
                    <td className="py-2 px-3">
                      {r.status === "PAID" ? (
                        <span className="text-emerald-400">
                          Pagata il {formatDate(r.paid_at)}
                          <span className="block text-[10px] text-slate-500">
                            {SOURCE_LABELS[r.payment_source ?? ""] ?? r.payment_source}
                            {r.confirmed_by ? ` · ${r.confirmed_by}` : ""}
                          </span>
                        </span>
                      ) : r.status === "FAILED" ? (
                        <span className="text-rose-400">Addebito non riuscito</span>
                      ) : (
                        <span className="text-slate-500">In attesa</span>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      {r.commission_released_at ? (
                        <span className="text-emerald-400">Partite il {formatDate(r.commission_released_at)}</span>
                      ) : r.commission_pending ? (
                        <span className="text-sky-400">In calcolo…</span>
                      ) : r.status === "PAID" ? (
                        <span className="text-amber-400">All&apos;attivazione del contratto</span>
                      ) : (
                        <span className="text-slate-500">Alla rata incassata</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right">
                      {r.status !== "PAID" && (
                        <button
                          onClick={() => handleConfirm(r.number)}
                          disabled={confirming === r.number}
                          className="px-2.5 py-1 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50 whitespace-nowrap"
                        >
                          {confirming === r.number ? "..." : "Conferma rata ricevuta"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
