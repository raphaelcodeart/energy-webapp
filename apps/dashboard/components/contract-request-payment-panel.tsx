"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { formatEuroCents as euro } from "@/lib/product-audience";
import type { ContractRequestPaymentOptionsRead } from "@/lib/types";

function lialCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} LialCash`;
}

export function useRequestPaymentOptions(requestId: string) {
  return useQuery<ContractRequestPaymentOptionsRead>({
    queryKey: ["contract-request", requestId, "payment-options"],
    queryFn: async () => {
      const res = await fetch(`/api/proxy/contract-requests/${requestId}/payment-options`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
    // Payment happens in another tab and is confirmed by a webhook a few
    // seconds later: coming back to this tab must show it.
    refetchOnWindowFocus: true,
  });
}

/** "Paga la pratica": one payment for every contract of the pratica that is
 *  sent and not paid yet (Session 52).
 *
 *  The customer sees one figure -- the whole pratica, or its monthly
 *  instalment -- and the list of what it covers. Behind it every contract
 *  receives exactly its own share, and every amount on this screen comes
 *  from the server: the browser only sends back a plan key, and only the
 *  signed Stripe webhook marks anything paid.
 */
export function ContractRequestPaymentPanel({ requestId }: { requestId: string }) {
  const { data, error } = useRequestPaymentOptions(requestId);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);
  const [opened, setOpened] = useState(false);

  async function handlePay() {
    if (!selected) return;
    setLoading(true);
    setPayError(null);
    try {
      const origin = window.location.origin;
      const successUrl = `${origin}/customer?tab=contracts&payment=success`;
      const cancelUrl = `${origin}/customer?tab=contracts&payment=cancelled`;
      const res = await fetch(
        `/api/proxy/contract-requests/${requestId}/checkout-session?success_url=${encodeURIComponent(successUrl)}&cancel_url=${encodeURIComponent(cancelUrl)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ payment_plan: selected }),
        }
      );
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { checkout_url } = await res.json();
      // A new tab, never a redirect: the pratica the customer is looking at
      // stays where it is.
      window.open(checkout_url, "_blank", "noopener,noreferrer");
      setOpened(true);
    } catch (err: any) {
      setPayError(err.message || "Impossibile avviare il pagamento.");
    } finally {
      setLoading(false);
    }
  }

  if (error) return <p className="text-sm text-rose-400">{(error as Error).message}</p>;
  if (!data) return <div className="h-32 rounded-2xl bg-white/5 light:bg-slate-900/5 animate-pulse" />;

  if (data.lines.length === 0) {
    return (
      <div className="rounded-2xl p-5 border border-emerald-500/25 bg-emerald-500/10">
        <p className="text-sm font-semibold text-emerald-400">
          {data.points_paid > 0 ? "Pagamento ricevuto" : "Niente da pagare in questo momento"}
        </p>
        <p className="text-xs text-slate-300 light:text-slate-600 mt-1">
          {data.points_paid > 0
            ? "Ogni contratto si attiva appena l'amministrazione approva i suoi documenti. Se ne mancano ancora, puoi caricarli quando vuoi."
            : "I contratti di questa pratica non sono in attesa di pagamento."}
        </p>
      </div>
    );
  }

  if (!data.card_available) {
    return (
      <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <p className="text-sm text-amber-400">
          Il pagamento con carta non è ancora attivo. Contatta l&apos;assistenza per completare l&apos;attivazione.
        </p>
      </div>
    );
  }

  return (
    <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <h4 className="text-sm font-semibold text-white light:text-slate-900">Scegli come pagare</h4>
      <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
        Un solo pagamento per {data.lines.length === 1 ? "il contratto" : `tutti i ${data.lines.length} contratti`} della
        pratica. Ogni contratto resta indipendente: si attiva quando i suoi documenti sono approvati.
      </p>

      <div className="mt-3 rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
        {data.lines.map((line) => (
          <div key={line.contract_id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
            <span className="text-slate-300 light:text-slate-600 min-w-0 truncate">{line.label}</span>
            <span className="text-white light:text-slate-900 font-semibold tabular-nums shrink-0">{euro(line.gross_cents)}</span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
          <span className="font-semibold text-slate-300 light:text-slate-600">Totale</span>
          <span className="font-bold text-white light:text-slate-900 tabular-nums">{euro(data.total_gross_cents)}</span>
        </div>
      </div>

      {data.cashback_total_cents > 0 && (
        <div className="mt-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
          <p className="text-xs text-emerald-400 font-semibold">
            Ricevi in cashback: {lialCash(data.cashback_total_cents)}
          </p>
          <p className="text-[10px] text-slate-400 light:text-slate-500 mt-0.5">
            Accreditato in automatico sul tuo wallet appena paghi — con le rate, a ogni rata pagata.
          </p>
        </div>
      )}

      <div className="space-y-2.5 mt-4">
        {data.options.map((option) => {
          const isSelected = selected === option.key;
          return (
            <button
              key={option.key}
              onClick={() => option.available && setSelected(option.key)}
              disabled={!option.available}
              className={`w-full text-left p-4 rounded-xl border transition ${
                !option.available
                  ? "opacity-50 cursor-not-allowed bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300"
                  : isSelected
                    ? "cursor-pointer bg-orange-500/10 border-orange-500/50"
                    : "cursor-pointer bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 hover:bg-white/10"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white light:text-slate-900">{option.label}</p>
                  <p className="text-[11px] text-slate-400 light:text-slate-500 mt-0.5">
                    {option.available ? option.description : option.unavailable_reason}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-lg font-bold text-orange-400 tabular-nums">{euro(option.instalment_cents)}</p>
                  {option.instalments > 1 && <p className="text-[10px] text-slate-500">al mese × {option.instalments}</p>}
                </div>
              </div>
              {option.instalments > 1 && (
                <p className="text-[10px] text-slate-500 mt-2 pt-2 border-t border-white/5 light:border-slate-200">
                  Totale {euro(option.total_cents)}
                  {option.rounding_difference_cents !== 0 && (
                    <span className="text-slate-600">
                      {" "}({option.rounding_difference_cents > 0 ? "+" : ""}
                      {(option.rounding_difference_cents / 100).toFixed(2).replace(".", ",")} € per arrotondamento delle rate)
                    </span>
                  )}
                </p>
              )}
            </button>
          );
        })}
      </div>

      {payError && (
        <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{payError}</div>
      )}

      <button
        onClick={handlePay}
        disabled={!selected || loading}
        className="w-full mt-4 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 py-2.5 text-sm font-semibold text-white shadow-lg transition disabled:opacity-50 cursor-pointer"
      >
        {loading ? "Apertura del pagamento..." : "Paga con carta"}
      </button>
      <p className="text-[10px] text-slate-500 mt-2 text-center">
        {opened
          ? "Completa il pagamento nella scheda che si è aperta, poi torna qui: questa pagina si aggiorna da sola."
          : "Il pagamento si apre in una nuova scheda. Non serve aspettare l'approvazione dei documenti."}
      </p>
    </div>
  );
}
