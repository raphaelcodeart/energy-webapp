"use client";

import { useState } from "react";
import { friendlyApiError } from "@/lib/api-error";

type DriveResult = {
  folder_name: string;
  folder_url: string;
  uploaded: number;
  replaced: number;
};

/** "Scarica tutto" e "Invia su Drive", per l'amministrazione.

    Stesso fascicolo per entrambi -- tutti gli allegati più un PDF
    riassuntivo del contratto e del cliente -- perché a costruirlo è lo
    stesso modulo lato server (`contracts/dossier.py`). Cambia solo dove
    finisce: un file zip sul computer di chi clicca, o una cartella
    `<nome cliente>-<id contratto>` su Google Drive. */
export function ContractDossierActions({ contractId }: { contractId: string }) {
  const [downloading, setDownloading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drive, setDrive] = useState<DriveResult | null>(null);

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/dossier.zip`);
      if (!res.ok) throw new Error(await friendlyApiError(res));

      // Il nome giusto ("Mario Rossi-<id>.zip") lo decide il server e viaggia
      // nel Content-Disposition: qui si legge quello, non si ricostruisce.
      // filename*= (UTF-8) ha la precedenza su filename=, che è la versione
      // ripulita per i client vecchi.
      const disposition = res.headers.get("content-disposition") ?? "";
      const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
      const plain = /filename="([^"]+)"/i.exec(disposition);
      const filename =
        (utf8?.[1] && decodeURIComponent(utf8[1])) || plain?.[1] || `contratto-${contractId}.zip`;

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err?.message || "Impossibile scaricare il fascicolo.");
    } finally {
      setDownloading(false);
    }
  }

  async function handleSendToDrive() {
    setSending(true);
    setError(null);
    setDrive(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/dossier/drive`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setDrive(await res.json());
    } catch (err: any) {
      setError(err?.message || "Impossibile inviare il fascicolo su Drive.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" />
          </svg>
          {downloading ? "Preparazione..." : "Scarica tutto (ZIP)"}
        </button>

        <button
          onClick={handleSendToDrive}
          disabled={sending}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
          </svg>
          {sending ? "Invio in corso..." : "Invia su Drive"}
        </button>
      </div>

      <p className="text-[10px] text-slate-500">
        Tutti i documenti allegati più un PDF riassuntivo del contratto e del cliente. Su Drive
        finiscono in una cartella chiamata come l&apos;archivio.
      </p>

      {drive && (
        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
          <p className="font-semibold">Fascicolo su Drive: {drive.folder_name}</p>
          <p className="mt-0.5 text-emerald-400/80">
            {drive.uploaded} file caricati
            {drive.replaced > 0 && `, ${drive.replaced} aggiornati`}.
          </p>
          <a
            href={drive.folder_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block mt-1.5 underline font-semibold"
          >
            Apri la cartella su Drive
          </a>
        </div>
      )}

      {error && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
          {error}
        </div>
      )}
    </div>
  );
}
