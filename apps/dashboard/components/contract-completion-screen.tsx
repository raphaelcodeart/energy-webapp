"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ContractDocumentsPanel, useContractDocuments } from "@/components/contract-documents-panel";
import { ContractPaymentPanel } from "@/components/contract-payment-panel";
import { FullScreenPanel, FullScreenSteps } from "@/components/full-screen-panel";
import type { ContractPaymentOptionsRead } from "@/lib/types";

/** Statuses at which the contract is waiting on the customer (or on us) for
    something -- the ones worth putting a "finish this" button in front of.
    Anything else (ACTIVE, CANCELLED, REJECTED...) is history and gets the
    ordinary inline document list instead. */
export const ACTIONABLE_CONTRACT_STATUSES = new Set([
  "DRAFT",
  "SUBMITTED",
  "DOCUMENTS_PENDING",
  "UNDER_REVIEW",
  "APPROVED",
  "PAYMENT_PENDING",
]);

const STEPS = ["Documenti", "Verifica", "Pagamento"];

function stepIndexFor(status: string): number {
  if (status === "UNDER_REVIEW") return 1;
  if (status === "APPROVED" || status === "PAYMENT_PENDING") return 2;
  return 0;
}

/** The banner that replaces the old inline pile of panels: one sentence
    saying what is actually left to do, and one button that opens the whole
    thing full-screen.

    The count comes from the same query the document list uses, so the
    card and the list can never disagree about how many are missing. */
export function ContractCompletionCard({
  contractId,
  status,
  productName,
}: {
  contractId: string;
  status: string;
  productName: string;
}) {
  const [open, setOpen] = useState(false);
  const { data } = useContractDocuments(contractId);
  // Same query key as ContractPaymentPanel, so the card and the panel share
  // one fetch and can never disagree about whether it has been paid.
  const { data: payment } = useQuery<ContractPaymentOptionsRead>({
    queryKey: ["contract", contractId, "payment-options"],
    queryFn: async () => {
      const res = await fetch(`/api/proxy/contracts/mine/${contractId}/payment-options`);
      if (!res.ok) throw new Error("Impossibile caricare le modalità di pagamento.");
      return res.json();
    },
  });
  const paid = Boolean(payment?.paid_at);
  const canPayNow = Boolean(payment?.payable && payment?.card_available);

  const requiredRows = (data?.required ?? []).filter((row) => row.required !== false);
  const missing = requiredRows.filter((row) => row.document === null).length;
  const step = stepIndexFor(status);

  let headline: string;
  let body: string;
  let cta: string;
  if (step === 2) {
    headline = "Scegli come pagare";
    body =
      "I tuoi documenti sono stati approvati. Ultimo passaggio: scegli se pagare in soluzione unica, in 3 rate o in 12 rate mensili.";
    cta = "Paga e attiva il contratto";
  } else if (step === 1) {
    headline = paid ? "Pagato — documenti in verifica" : "Documenti in verifica";
    body = paid
      ? "Abbiamo ricevuto documenti e pagamento. Il contratto si attiva appena l'amministrazione approva i documenti."
      : "Abbiamo ricevuto i documenti e l'amministrazione li sta controllando. Intanto puoi già pagare: il contratto si attiva appena sono approvati.";
    cta = paid ? "Vedi il contratto" : "Paga ora";
  } else if (!data) {
    // Still loading the document list -- say the true thing that needs no
    // count rather than flashing "Mancano 0 documenti".
    headline = "Completa il contratto";
    body = "Carica i documenti dell'intestatario per completare l'attivazione.";
    cta = "Completa il contratto";
  } else if (missing > 0) {
    headline =
      (missing === 1 ? "Manca 1 documento" : `Mancano ${missing} documenti`) + (paid ? " — pagamento ricevuto" : "");
    body = paid
      ? "Hai già pagato: per attivare il contratto servono ancora i documenti dell'intestatario. Puoi caricarli anche in più momenti."
      : canPayNow
        ? "Per attivare il contratto servono i documenti dell'intestatario, ma puoi già pagare adesso e caricarli dopo."
        : "Per completare l'attivazione servono i documenti dell'intestatario. Puoi caricarli anche in più momenti: quello che carichi resta salvato.";
    cta = "Completa il contratto";
  } else {
    headline = "Quasi fatto";
    body = "Hai caricato tutti i documenti obbligatori. Controlla che sia tutto corretto e invia.";
    cta = "Rivedi e completa";
  }

  return (
    <>
      <div className="p-4 sm:p-5 rounded-2xl border border-orange-500/25 bg-gradient-to-br from-orange-600/10 to-amber-500/5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-white light:text-slate-900">{headline}</p>
            <p className="text-xs text-slate-400 light:text-slate-600 mt-1 max-w-xl">{body}</p>
            <div className="mt-3">
              <FullScreenSteps steps={STEPS} current={step} />
            </div>
          </div>
          <button
            onClick={() => setOpen(true)}
            className="shrink-0 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition cursor-pointer"
          >
            {cta}
          </button>
        </div>
      </div>

      {open && (
        <FullScreenPanel
          eyebrow="Completa il contratto"
          title={productName}
          onClose={() => setOpen(false)}
          subtitle={<FullScreenSteps steps={STEPS} current={step} />}
        >
          <div className="space-y-8">
            <section>
              <h3 className="text-sm font-bold text-white light:text-slate-900">Documenti</h3>
              <p className="text-xs text-slate-400 light:text-slate-500 mt-1 mb-3">
                Carica una foto nitida o un PDF di ogni documento. Se serve allegare altro, usa
                “Aggiungi un altro documento” in fondo.
              </p>
              <ContractDocumentsPanel contractId={contractId} />
            </section>

            <section>
              <h3 className="text-sm font-bold text-white light:text-slate-900">Pagamento</h3>
              {/* Rendered at every stage: payment is accepted before the
                  documents are approved (Session 49), and once paid the
                  panel says so instead of offering the plans again. */}
              <div className="mt-3">
                <ContractPaymentPanel contractId={contractId} />
              </div>
            </section>

            <button
              onClick={() => setOpen(false)}
              className="w-full rounded-xl bg-white/10 light:bg-slate-900/5 hover:bg-white/20 py-2.5 text-xs font-semibold text-white light:text-slate-700 transition cursor-pointer"
            >
              Chiudi — quello che hai caricato resta salvato
            </button>
          </div>
        </FullScreenPanel>
      )}
    </>
  );
}
