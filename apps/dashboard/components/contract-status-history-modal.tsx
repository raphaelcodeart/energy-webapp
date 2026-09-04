"use client";

import { useQuery } from "@tanstack/react-query";
import type { ContractStatusHistoryRead } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

function label(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

async function fetchStatusHistory(contractId: string): Promise<ContractStatusHistoryRead[]> {
  const res = await fetch(`/api/proxy/contracts/${contractId}/status-history`);
  if (!res.ok) throw new Error("Impossibile caricare lo storico del contratto.");
  return res.json();
}

export function ContractStatusHistoryModal({
  contractId,
  onClose,
}: {
  contractId: string;
  onClose: () => void;
}) {
  const { data: history, error, isLoading } = useQuery({
    queryKey: ["admin", "contracts", "status-history", contractId],
    queryFn: () => fetchStatusHistory(contractId),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-lg max-h-[85vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <h3 className="text-lg font-bold text-white light:text-slate-900">Storico stato contratto</h3>
            <div className="font-mono text-[10px] text-slate-500 mt-1">{contractId}</div>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer shrink-0"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {error && (
          <p className="text-sm text-rose-400 mb-4">Impossibile caricare lo storico di questo contratto.</p>
        )}
        {isLoading && <p className="text-sm text-slate-500 py-8 text-center">Caricamento...</p>}
        {!isLoading && history && history.length === 0 && (
          <p className="text-sm text-slate-500 py-8 text-center">Nessun passaggio di stato registrato.</p>
        )}

        {!isLoading && history && history.length > 0 && (
          <ol className="relative border-l border-white/10 light:border-slate-300 ml-2 space-y-6">
            {history.map((h) => (
              <li key={h.id} className="ml-4">
                <span className="absolute -left-[5px] mt-1.5 w-2.5 h-2.5 rounded-full bg-orange-500" />
                <div className="flex items-center gap-2 flex-wrap">
                  {h.from_status && (
                    <>
                      <span className="text-xs text-slate-400 light:text-slate-500">{label(h.from_status)}</span>
                      <span className="text-slate-600">→</span>
                    </>
                  )}
                  <span className="text-sm font-semibold text-white light:text-slate-900">{label(h.to_status)}</span>
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  {new Date(h.created_at).toLocaleString("it-IT")} · {h.actor_name}
                </div>
                {h.reason && (
                  <div className="text-xs text-slate-300 light:text-slate-600 mt-1">
                    <span className="text-slate-500">Motivazione: </span>{h.reason}
                  </div>
                )}
                {h.notes && (
                  <div className="text-xs text-slate-400 light:text-slate-500 mt-1">
                    <span className="text-slate-500">Note: </span>{h.notes}
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
