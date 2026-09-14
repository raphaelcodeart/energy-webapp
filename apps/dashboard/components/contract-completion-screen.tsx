"use client";

import { useState } from "react";
import { ContractDocumentsPanel, useContractDocuments } from "@/components/contract-documents-panel";
import { ContractPaymentPanel } from "@/components/contract-payment-panel";
import { FullScreenPanel, FullScreenSteps } from "@/components/full-screen-panel";

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
    headline = "Documenti in verifica";
    body =
      "Abbiamo ricevuto tutto. L'amministrazione sta controllando i documenti: appena sono approvati potrai scegliere come pagare.";
    cta = "Vedi i documenti caricati";
  } else if (!data) {
    // Still loading the document list -- say the true thing that needs no
    // count rather than flashing "Mancano 0 documenti".
    headline = "Completa il contratto";
    body = "Carica i documenti dell'intestatario per completare l'attivazione.";
    cta = "Completa il contratto";
  } else if (missing > 0) {
    headline = missing === 1 ? "Manca 1 documento" : `Mancano ${missing} documenti`;
    body =
      "Per completare l'attivazione servono i documenti dell'intestatario. Puoi caricarli anche in più momenti: quello che carichi resta salvato.";
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
              {/* Rendered at every stage, not only at PAYMENT_PENDING: the
                  panel's own job is to say what is still missing, and
                  showing the step greyed-out with an explanation beats
                  hiding it and leaving the customer wondering when, or
                  whether, they will be asked to pay. */}
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
