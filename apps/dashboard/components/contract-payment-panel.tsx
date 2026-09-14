"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { formatEuroCents as euro } from "@/lib/product-audience";
import type { ContractPaymentOptionsRead } from "@/lib/types";

async function fetchOptions(contractId: string): Promise<ContractPaymentOptionsRead> {
  const res = await fetch(`/api/proxy/contracts/mine/${contractId}/payment-options`);
  if (!res.ok) throw new Error("Impossibile caricare le modalità di pagamento.");
  return res.json();
}

/** "Paga il contratto": the step after the documents have been uploaded and
 *  an administrator has approved them.
 *
 *  Every amount on this screen comes from the server, computed from the
 *  figure frozen on this contract. The browser only ever sends back a plan
 *  key -- it never proposes a price, and it never marks anything paid: the
 *  contract stays in "attesa di pagamento" until Stripe's signed webhook
 *  says otherwise, so reloading the success page does nothing.
 */
export function ContractPaymentPanel({ contractId }: { contractId: string }) {
  const { data, error } = useQuery({
    queryKey: ["contract", contractId, "payment-options"],
    queryFn: () => fetchOptions(contractId),
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  async function handlePay() {
    if (!selected) return;
    setLoading(true);
    setPayError(null);
    try {
      const base = new URL(window.location.origin);
      const successUrl = `${base.origin}/customer?tab=lial-contracts&payment=success`;
      const cancelUrl = `${base.origin}/customer?tab=lial-contracts&payment=cancelled`;
      const res = await fetch(
        `/api/proxy/contracts/mine/${contractId}/checkout-session?success_url=${encodeURIComponent(successUrl)}&cancel_url=${encodeURIComponent(cancelUrl)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ payment_plan: selected }),
        }
      );
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { checkout_url } = await res.json();
      // A new tab, never a redirect: if Stripe fails or the customer changes
      // their mind, the dashboard they were on is still there. Same rule as
      // the Shop checkout.
      window.open(checkout_url, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setPayError(err.message || "Impossibile avviare il pagamento.");
    } finally {
      setLoading(false);
    }
  }

  if (error) return <p className="text-sm text-rose-400">Impossibile caricare le modalità di pagamento.</p>;
  if (!data) return <div className="h-32 rounded-2xl bg-white/5 light:bg-slate-900/5 animate-pulse" />;

  if (!data.payable) {
    return (
      <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <p className="text-sm text-slate-400 light:text-slate-500">
          {data.missing_amount
            ? "Questo contratto è pronto per il pagamento, ma non ha un importo registrato: è stato creato prima che il sistema iniziasse a fissare il prezzo sul contratto. Contatta l'assistenza, lo sistemiamo noi."
            : data.status === "DOCUMENTS_PENDING" || data.status === "SUBMITTED"
            ? "Carica i documenti richiesti: appena l'amministrazione li approva potrai scegliere come pagare."
            : data.status === "UNDER_REVIEW"
              ? "I tuoi documenti sono in verifica. Appena approvati potrai scegliere come pagare."
              : "Questo contratto non è in attesa di pagamento."}
        </p>
      </div>
    );
  }

  if (!data.card_available) {
    return (
      <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <p className="text-sm text-amber-400">
          Il pagamento con carta non è ancora attivo. Contatta l&apos;assistenza per completare
          l&apos;attivazione del contratto.
        </p>
      </div>
    );
  }

  return (
    <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <h4 className="text-sm font-semibold text-white light:text-slate-900">Scegli come pagare</h4>
      <p className="text-xs text-slate-400 light:text-slate-500 mt-1 mb-4">
        Totale del contratto: <strong className="text-white light:text-slate-900">{euro(data.gross_amount_cents ?? 0)}</strong>
      </p>

      <div className="space-y-2.5">
        {data.options.map((option) => {
          const isSelected = selected === option.key;
          return (
            <button
              key={option.key}
              onClick={() => setSelected(option.key)}
              className={`w-full text-left p-4 rounded-xl border transition cursor-pointer ${
                isSelected
                  ? "bg-orange-500/10 border-orange-500/50"
                  : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 hover:bg-white/10"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white light:text-slate-900">{option.label}</p>
                  <p className="text-[11px] text-slate-400 light:text-slate-500 mt-0.5">{option.description}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-lg font-bold text-orange-400 tabular-nums">
                    {euro(option.instalment_cents)}
                  </p>
                  {option.instalments > 1 && (
                    <p className="text-[10px] text-slate-500">
                      al mese × {option.instalments}
                    </p>
                  )}
                </div>
              </div>
              {option.instalments > 1 && (
                <p className="text-[10px] text-slate-500 mt-2 pt-2 border-t border-white/5 light:border-slate-200">
                  Totale {euro(option.total_cents)}
                  {/* Splitting an amount into equal instalments rarely lands
                      exactly on the contract total. The difference is a few
                      cents at most, and it is said out loud rather than
                      quietly absorbed. */}
                  {option.rounding_difference_cents !== 0 && (
                    <span className="text-slate-600">
                      {" "}({option.rounding_difference_cents > 0 ? "+" : ""}
                      {(option.rounding_difference_cents / 100).toFixed(2).replace(".", ",")} € per
                      arrotondamento della rata)
                    </span>
                  )}
                </p>
              )}
            </button>
          );
        })}
      </div>

      {payError && (
        <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
          {payError}
        </div>
      )}

      <button
        onClick={handlePay}
        disabled={!selected || loading}
        className="w-full mt-4 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 py-2.5 text-sm font-semibold text-white shadow-lg transition disabled:opacity-50 cursor-pointer"
      >
        {loading ? "Apertura del pagamento..." : "Paga con carta"}
      </button>
      <p className="text-[10px] text-slate-500 mt-2 text-center">
        Il pagamento si apre in una nuova scheda. Il contratto risulta attivo solo quando la banca
        conferma l&apos;addebito.
      </p>
    </div>
  );
}
