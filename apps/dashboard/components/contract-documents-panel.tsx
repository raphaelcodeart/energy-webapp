"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";

type DocumentRead = {
  id: string;
  /** Exactly one of these two is set: a document of one contract, or of its
      whole pratica (Session 52), which then counts for every point in it. */
  contract_id: string | null;
  contract_request_id: string | null;
  document_type: string;
  /** Only ever set on an extra attachment -- what its uploader called it. */
  description: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_by_user_id: string;
  uploaded_by_role: string;
  uploaded_by_name: string | null;
  status: string;
  reviewed_by_user_id: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
};

type RequiredDocumentStatus = {
  document_type: string;
  /** False for a slot that is offered but never blocks the contract (the
      visura of a ditta individuale). Older responses omit it; the server
      defaults it to true, and so does the destructuring below. */
  required?: boolean;
  document: DocumentRead | null;
};

type ContractDocumentsRead = {
  contract_id?: string | null;
  contract_request_id?: string | null;
  required: RequiredDocumentStatus[];
  extra?: DocumentRead[];
};

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  IDENTITY: "Documento d'identità",
  FISCAL_CODE: "Codice fiscale",
  UTILITY_BILL: "Fattura luce/gas",
  CHAMBER_OF_COMMERCE: "Visura camerale",
  OTHER: "Documento aggiuntivo",
};

/** What each slot is for, in the words a customer standing at a scanner
    would use. Shown under the title so nobody has to guess whether "Fattura
    luce/gas" means theirs or the one they are switching away from. */
const DOCUMENT_TYPE_HINTS: Record<string, string> = {
  IDENTITY: "Carta d'identità, patente o passaporto dell'intestatario, in corso di validità.",
  FISCAL_CODE: "Tessera sanitaria o codice fiscale dell'intestatario.",
  UTILITY_BILL: "Una bolletta recente della fornitura da attivare o cambiare.",
  CHAMBER_OF_COMMERCE: "Visura camerale dell'azienda, possibilmente non più vecchia di sei mesi.",
};

const STATUS_LABELS: Record<string, string> = {
  PENDING_REVIEW: "In attesa di verifica",
  APPROVED: "Approvato",
  REJECTED: "Respinto",
};

const ACCEPTED_CONTENT_TYPES = "application/pdf,image/jpeg,image/png";
const MIN_DESCRIPTION_LENGTH = 3;
const MAX_DESCRIPTION_LENGTH = 120;

function statusColor(status: string): string {
  if (status === "APPROVED") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  if (status === "REJECTED") return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  if (status === "MISSING") return "bg-white/5 light:bg-slate-900/5 text-slate-400 border-white/10 light:border-slate-300";
  return "bg-amber-500/10 text-amber-400 border-amber-500/20";
}

async function fetchDocuments(path: string): Promise<ContractDocumentsRead> {
  const res = await fetch(path);
  if (!res.ok) throw new Error("Impossibile caricare i documenti.");
  return res.json();
}

function documentsPath({ contractId, requestId }: { contractId?: string; requestId?: string }): string {
  return contractId
    ? `/api/proxy/contracts/${contractId}/documents`
    : `/api/proxy/contract-requests/${requestId}/documents`;
}

async function fetchDocumentUrl(documentId: string): Promise<string> {
  const res = await fetch(`/api/proxy/documents/${documentId}/url`);
  if (!res.ok) throw new Error("Impossibile aprire il documento.");
  const data = await res.json();
  return data.url;
}

/** How many of the documents that actually block this contract are in.
    Exported because the contract card outside this panel says the same
    thing ("mancano 2 documenti") and must never disagree with it. */
export function missingRequiredCount(data: ContractDocumentsRead | undefined): number {
  if (!data) return 0;
  return data.required.filter((row) => row.required !== false && row.document === null).length;
}

export function useContractDocuments(contractId: string) {
  return useQuery({
    queryKey: ["documents", "contract", contractId],
    queryFn: () => fetchDocuments(documentsPath({ contractId })),
  });
}

/** The documents uploaded once for a whole pratica (Session 52). */
export function useRequestDocuments(requestId: string) {
  return useQuery({
    queryKey: ["documents", "request", requestId],
    queryFn: () => fetchDocuments(documentsPath({ requestId })),
  });
}

/** One contract's documents (`contractId`) or a pratica's shared ones
    (`requestId`) -- same slots, same upload, same review.

    `onlyTypes` narrows the slots shown, for a screen that is about one
    supply point: there the identity and fiscal code already live on the
    pratica, and only the point's own bill belongs. */
export function ContractDocumentsPanel({
  contractId,
  requestId,
  isStaff = false,
  onlyTypes,
}: {
  contractId?: string;
  requestId?: string;
  isStaff?: boolean;
  onlyTypes?: string[];
}) {
  const queryClient = useQueryClient();
  const contractQuery = useQuery({
    queryKey: ["documents", "contract", contractId],
    queryFn: () => fetchDocuments(documentsPath({ contractId })),
    enabled: Boolean(contractId),
  });
  const requestQuery = useQuery({
    queryKey: ["documents", "request", requestId],
    queryFn: () => fetchDocuments(documentsPath({ requestId })),
    enabled: !contractId && Boolean(requestId),
  });
  const { data: rawData, error, isLoading } = contractId ? contractQuery : requestQuery;
  const ownerKey = contractId ?? requestId ?? "";
  const data = rawData && onlyTypes
    ? { ...rawData, required: rawData.required.filter((row) => onlyTypes.includes(row.document_type)) }
    : rawData;

  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [extraLabel, setExtraLabel] = useState("");
  const [addingExtra, setAddingExtra] = useState(false);
  const extraFileInput = useRef<HTMLInputElement>(null);

  const trimmedExtraLabel = extraLabel.trim();
  const canPickExtraFile = trimmedExtraLabel.length >= MIN_DESCRIPTION_LENGTH;

  async function refresh() {
    // Every contract of a pratica shows the pratica's documents too, and the
    // pratica screens count what is missing: all of it is stale now.
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["documents"] }),
      queryClient.invalidateQueries({ queryKey: ["contract-request"] }),
      queryClient.invalidateQueries({ queryKey: ["contract-requests"] }),
    ]);
  }

  async function handleUpload(documentType: string, file: File, description?: string) {
    setUploadingType(documentType);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("document_type", documentType);
      if (description) formData.append("description", description);
      formData.append("file", file);
      const res = await fetch(documentsPath({ contractId, requestId }), { method: "POST", body: formData });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
      return true;
    } catch (err: any) {
      // The server's own message when there is one (a file too large, a
      // label too short) -- it says something the generic sentence can't.
      setUploadError(err?.message || `${DOCUMENT_TYPE_LABELS[documentType] ?? documentType}: caricamento fallito.`);
      return false;
    } finally {
      setUploadingType(null);
    }
  }

  async function handleExtraUpload(file: File) {
    const ok = await handleUpload("OTHER", file, trimmedExtraLabel);
    if (ok) {
      setExtraLabel("");
      setAddingExtra(false);
    }
  }

  async function handleView(documentId: string) {
    try {
      const url = await fetchDocumentUrl(documentId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      setUploadError("Impossibile aprire il documento.");
    }
  }

  async function handleReview(documentId: string, newStatus: "APPROVED" | "REJECTED") {
    try {
      const res = await fetch(`/api/proxy/documents/${documentId}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, review_note: reviewNote || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReviewingId(null);
      setReviewNote("");
      await refresh();
    } catch {
      setUploadError("Impossibile aggiornare lo stato del documento.");
    }
  }

  /** The staff-only Approva/Respingi strip, identical for a slot document
      and for an extra attachment. */
  function reviewControls(doc: DocumentRead) {
    if (!isStaff || doc.status !== "PENDING_REVIEW") return null;
    return (
      <div className="mt-3 pt-3 border-t border-white/5 light:border-slate-200 space-y-2">
        {reviewingId === doc.id ? (
          <>
            <input
              value={reviewNote}
              onChange={(e) => setReviewNote(e.target.value)}
              placeholder="Nota (opzionale)..."
              className="w-full rounded-lg glass-input px-3 py-1.5 text-xs focus:border-orange-500"
            />
            <div className="flex gap-2">
              <button
                onClick={() => handleReview(doc.id, "APPROVED")}
                className="px-3 py-1 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer"
              >
                Approva
              </button>
              <button
                onClick={() => handleReview(doc.id, "REJECTED")}
                className="px-3 py-1 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer"
              >
                Respingi
              </button>
              <button
                onClick={() => { setReviewingId(null); setReviewNote(""); }}
                className="px-3 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 text-xs font-semibold transition cursor-pointer"
              >
                Annulla
              </button>
            </div>
          </>
        ) : (
          <button
            onClick={() => setReviewingId(doc.id)}
            className="px-3 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
          >
            Verifica documento
          </button>
        )}
      </div>
    );
  }

  if (isLoading) return <p className="text-sm text-slate-500">Caricamento documenti...</p>;
  if (error) return <p className="text-sm text-rose-400">Impossibile caricare i documenti.</p>;
  if (!data) return null;

  const extra = data.extra ?? [];
  const requiredRows = data.required.filter((row) => row.required !== false);
  const uploadedRequired = requiredRows.filter((row) => row.document !== null).length;
  const missing = requiredRows.length - uploadedRequired;

  return (
    <div className="space-y-3">
      {/* What is still missing, said once at the top -- before this, the
          only way to know was to read four status badges and count. */}
      <div
        className={`flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl border text-xs ${
          missing === 0
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
            : "bg-amber-500/10 border-amber-500/20 text-amber-400"
        }`}
      >
        <span className="font-semibold">
          {missing === 0
            ? "Tutti i documenti obbligatori sono stati caricati."
            : missing === 1
              ? "Manca 1 documento obbligatorio."
              : `Mancano ${missing} documenti obbligatori.`}
        </span>
        <span className="font-bold tabular-nums shrink-0">
          {uploadedRequired}/{requiredRows.length}
        </span>
      </div>

      {uploadError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{uploadError}</div>
      )}

      {data.required.map((row) => {
        const doc = row.document;
        const isRequired = row.required !== false;
        const inputId = `doc-upload-${ownerKey}-${row.document_type}`;
        // On a contract, a slot filled by its pratica's document.
        const inherited = Boolean(contractId && doc?.contract_request_id);
        return (
          <div
            key={row.document_type}
            className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200"
          >
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-white light:text-slate-900">
                  {DOCUMENT_TYPE_LABELS[row.document_type] ?? row.document_type}
                  {!isRequired && (
                    <span className="ml-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
                      Facoltativo
                    </span>
                  )}
                </p>
                {!doc && DOCUMENT_TYPE_HINTS[row.document_type] && (
                  <p className="text-[11px] text-slate-400 light:text-slate-500 mt-0.5">
                    {DOCUMENT_TYPE_HINTS[row.document_type]}
                  </p>
                )}
                {doc && (
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {doc.original_filename} · caricato da {doc.uploaded_by_name ?? "—"} il{" "}
                    {new Date(doc.created_at).toLocaleDateString("it-IT")}
                    {inherited && " · vale per tutti i punti della pratica"}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusColor(doc?.status ?? "MISSING")}`}>
                  {doc ? STATUS_LABELS[doc.status] ?? doc.status : "Non caricato"}
                </span>
                {doc && (
                  <button
                    onClick={() => handleView(doc.id)}
                    className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
                  >
                    Visualizza
                  </button>
                )}
                <input
                  type="file"
                  accept={ACCEPTED_CONTENT_TYPES}
                  id={inputId}
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleUpload(row.document_type, file);
                    e.target.value = "";
                  }}
                />
                <label
                  htmlFor={inputId}
                  className="px-2.5 py-1 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold cursor-pointer transition"
                >
                  {uploadingType === row.document_type
                    ? "Caricamento..."
                    : inherited
                      ? "Carica per questo punto"
                      : doc
                        ? "Sostituisci"
                        : "Carica"}
                </label>
              </div>
            </div>

            {doc && doc.review_note && (
              <p className="text-[11px] text-slate-400 light:text-slate-500 mt-2">
                <span className="font-semibold">Nota amministrazione:</span> {doc.review_note}
              </p>
            )}

            {doc && reviewControls(doc)}
          </div>
        );
      })}

      {/* --- Allegati aggiuntivi ------------------------------------------
          Everything the fixed slots don't cover: the back of an ID, a
          delega, a lease, a visura somebody was asked for by hand. Each
          one is labelled by whoever uploads it, which is why the label is
          asked for BEFORE the file picker opens rather than after. */}
      <div className="pt-1">
        <p className="text-xs font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wider mb-2">
          Altri documenti allegati
        </p>

        {extra.length === 0 && !addingExtra && (
          <p className="text-[11px] text-slate-500 mb-2">
            Nessun allegato aggiuntivo. Puoi aggiungerne quanti ne servono.
          </p>
        )}

        <div className="space-y-2">
          {extra.map((doc) => (
            <div
              key={doc.id}
              className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200"
            >
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white light:text-slate-900">
                    {doc.description || DOCUMENT_TYPE_LABELS[doc.document_type] || doc.document_type}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {doc.original_filename} · caricato da {doc.uploaded_by_name ?? "—"} il{" "}
                    {new Date(doc.created_at).toLocaleDateString("it-IT")}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusColor(doc.status)}`}>
                    {STATUS_LABELS[doc.status] ?? doc.status}
                  </span>
                  <button
                    onClick={() => handleView(doc.id)}
                    className="px-2.5 py-1 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
                  >
                    Visualizza
                  </button>
                </div>
              </div>
              {doc.review_note && (
                <p className="text-[11px] text-slate-400 light:text-slate-500 mt-2">
                  <span className="font-semibold">Nota amministrazione:</span> {doc.review_note}
                </p>
              )}
              {reviewControls(doc)}
            </div>
          ))}
        </div>

        {addingExtra ? (
          <div className="mt-2 p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-orange-500/20 space-y-2">
            <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
              Che documento stai allegando?
            </label>
            <input
              autoFocus
              value={extraLabel}
              maxLength={MAX_DESCRIPTION_LENGTH}
              onChange={(e) => setExtraLabel(e.target.value)}
              placeholder="Es. Carta d'identità retro, Delega firmata, Contratto di locazione"
              className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
            />
            <p className="text-[10px] text-slate-500">
              Scrivi cos&apos;è, così l&apos;amministrazione sa cosa sta verificando. PDF, JPG o PNG, massimo 15 MB.
            </p>
            <input
              ref={extraFileInput}
              type="file"
              accept={ACCEPTED_CONTENT_TYPES}
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleExtraUpload(file);
                e.target.value = "";
              }}
            />
            <div className="flex gap-2">
              <button
                onClick={() => extraFileInput.current?.click()}
                disabled={!canPickExtraFile || uploadingType === "OTHER"}
                className="px-3 py-1.5 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {uploadingType === "OTHER" ? "Caricamento..." : "Scegli il file e carica"}
              </button>
              <button
                onClick={() => { setAddingExtra(false); setExtraLabel(""); }}
                className="px-3 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-slate-400 text-xs font-semibold transition cursor-pointer"
              >
                Annulla
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setAddingExtra(true)}
            className="mt-2 w-full px-3 py-2.5 rounded-xl border border-dashed border-white/15 light:border-slate-300 text-slate-300 light:text-slate-600 hover:border-orange-500/40 hover:text-orange-400 text-xs font-semibold transition cursor-pointer"
          >
            + Aggiungi un altro documento
          </button>
        )}
      </div>
    </div>
  );
}
