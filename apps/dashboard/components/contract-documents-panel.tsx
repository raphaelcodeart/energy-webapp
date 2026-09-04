"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";

type DocumentRead = {
  id: string;
  contract_id: string;
  document_type: string;
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
  document: DocumentRead | null;
};

type ContractDocumentsRead = {
  contract_id: string;
  required: RequiredDocumentStatus[];
};

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  IDENTITY: "Documento d'identità",
  FISCAL_CODE: "Codice fiscale",
  UTILITY_BILL: "Fattura luce/gas",
  CHAMBER_OF_COMMERCE: "Visura camerale",
};

const STATUS_LABELS: Record<string, string> = {
  PENDING_REVIEW: "In attesa di verifica",
  APPROVED: "Approvato",
  REJECTED: "Respinto",
};

function statusColor(status: string): string {
  if (status === "APPROVED") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  if (status === "REJECTED") return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  return "bg-amber-500/10 text-amber-400 border-amber-500/20";
}

async function fetchContractDocuments(contractId: string): Promise<ContractDocumentsRead> {
  const res = await fetch(`/api/proxy/contracts/${contractId}/documents`);
  if (!res.ok) throw new Error("Impossibile caricare i documenti.");
  return res.json();
}

async function fetchDocumentUrl(documentId: string): Promise<string> {
  const res = await fetch(`/api/proxy/documents/${documentId}/url`);
  if (!res.ok) throw new Error("Impossibile aprire il documento.");
  const data = await res.json();
  return data.url;
}

export function ContractDocumentsPanel({ contractId, isStaff = false }: { contractId: string; isStaff?: boolean }) {
  const queryClient = useQueryClient();
  const { data, error, isLoading } = useQuery({
    queryKey: ["documents", "contract", contractId],
    queryFn: () => fetchContractDocuments(contractId),
  });

  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["documents", "contract", contractId] });
  }

  async function handleUpload(documentType: string, file: File) {
    setUploadingType(documentType);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("document_type", documentType);
      formData.append("file", file);
      const res = await fetch(`/api/proxy/contracts/${contractId}/documents`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await refresh();
    } catch (err: any) {
      setUploadError(`${DOCUMENT_TYPE_LABELS[documentType] ?? documentType}: caricamento fallito.`);
    } finally {
      setUploadingType(null);
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

  if (isLoading) return <p className="text-sm text-slate-500">Caricamento documenti...</p>;
  if (error) return <p className="text-sm text-rose-400">Impossibile caricare i documenti.</p>;
  if (!data) return null;

  return (
    <div className="space-y-3">
      {uploadError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{uploadError}</div>
      )}
      {data.required.map((row) => {
        const doc = row.document;
        const inputId = `doc-upload-${contractId}-${row.document_type}`;
        return (
          <div
            key={row.document_type}
            className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200"
          >
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <p className="text-sm font-semibold text-white light:text-slate-900">
                  {DOCUMENT_TYPE_LABELS[row.document_type] ?? row.document_type}
                </p>
                {doc && (
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {doc.original_filename} · caricato da {doc.uploaded_by_name ?? "—"} il{" "}
                    {new Date(doc.created_at).toLocaleDateString("it-IT")}
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
                  accept="application/pdf,image/jpeg,image/png"
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
                  {uploadingType === row.document_type ? "Caricamento..." : doc ? "Sostituisci" : "Carica"}
                </label>
              </div>
            </div>

            {doc && doc.review_note && (
              <p className="text-[11px] text-slate-400 light:text-slate-500 mt-2">
                <span className="font-semibold">Nota amministrazione:</span> {doc.review_note}
              </p>
            )}

            {isStaff && doc && doc.status === "PENDING_REVIEW" && (
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
            )}
          </div>
        );
      })}
    </div>
  );
}
