"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";

export type GoogleDriveStatus = {
  configured: boolean;
  connected: boolean;
  account_email: string | null;
  connected_at: string | null;
  parent_folder_id: string | null;
  redirect_uri: string;
  client_id: string | null;
  client_secret_configured: boolean;
};

export async function fetchGoogleDriveStatus(): Promise<GoogleDriveStatus> {
  const res = await fetch("/api/proxy/integrations/google-drive");
  if (!res.ok) throw new Error("Impossibile leggere lo stato di Google Drive.");
  return res.json();
}

function CopyableValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <code className="flex-1 min-w-0 break-all px-2.5 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 text-[11px] text-slate-300 light:text-slate-600">
        {value}
      </code>
      <button
        type="button"
        onClick={async () => {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }}
        className="shrink-0 px-2.5 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-[11px] font-semibold transition cursor-pointer"
      >
        {copied ? "Copiato" : "Copia"}
      </button>
    </div>
  );
}

/** Collegamento a Google Drive, per il pulsante "Invia su Drive" sul
    fascicolo di un contratto.

    I campi sono volutamente non controllati (`defaultValue` + `key`): il
    valore iniziale arriva dal server e non c'è nessun `useEffect` che
    ricopia lo stato nella form, che in questo codebase è un errore di lint
    prima ancora che una cattiva idea. */
export function AdminGoogleDriveSettingsCard() {
  const queryClient = useQueryClient();
  const { data: status, error: loadError } = useQuery({
    queryKey: ["admin", "google-drive"],
    queryFn: fetchGoogleDriveStatus,
  });

  const [saving, setSaving] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setSaving(true);
    setError(null);
    try {
      // Il secret si invia solo se è stato digitato adesso: un campo lasciato
      // vuoto non deve cancellare un segreto già salvato (stessa regola delle
      // chiavi Stripe qui accanto).
      const body: Record<string, string> = {
        client_id: String(form.get("client_id") ?? "").trim(),
        parent_folder_id: String(form.get("parent_folder_id") ?? "").trim(),
      };
      const secret = String(form.get("client_secret") ?? "").trim();
      if (secret) body.client_secret = secret;

      const res = await fetch("/api/proxy/integrations/google-drive/credentials", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "google-drive"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: any) {
      setError(err?.message || "Impossibile salvare le credenziali Google.");
    } finally {
      setSaving(false);
    }
  }

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/integrations/google-drive/authorize-url", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const { url } = await res.json();
      // Stessa scheda, non una nuova: Google rimanda indietro alla pagina di
      // callback, e un popup bloccato lascerebbe l'amministratore a guardare
      // un pulsante che "non fa niente".
      window.location.href = url;
    } catch (err: any) {
      setError(err?.message || "Impossibile avviare il collegamento con Google.");
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    setError(null);
    try {
      const res = await fetch("/api/proxy/integrations/google-drive", { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "google-drive"] });
    } catch (err: any) {
      setError(err?.message || "Impossibile scollegare Google Drive.");
    }
  }

  return (
    <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <h3 className="text-sm font-semibold text-white light:text-slate-900">Google Drive</h3>
      <p className="text-xs text-slate-400 light:text-slate-500 mt-1 mb-4 max-w-2xl">
        Serve al pulsante <strong>&ldquo;Invia su Drive&rdquo;</strong> sul fascicolo di un contratto:
        crea una cartella <em>nome cliente-id contratto</em> con dentro tutti i documenti allegati e
        il PDF riassuntivo. I file finiscono sul Drive dell&apos;account che collega qui sotto.
      </p>

      {loadError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs mb-4">
          Impossibile leggere lo stato del collegamento.
        </div>
      )}

      {status && (
        <>
          <div
            className={`flex items-center justify-between gap-3 flex-wrap p-3 rounded-xl border text-xs mb-4 ${
              status.connected
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                : "bg-amber-500/10 border-amber-500/20 text-amber-400"
            }`}
          >
            <span className="font-semibold">
              {status.connected
                ? `Collegato a ${status.account_email ?? "un account Google"}`
                : status.configured
                  ? "Credenziali inserite. Manca solo l'autorizzazione."
                  : "Non configurato: inserisci Client ID e Client Secret qui sotto."}
            </span>
            <div className="flex gap-2 shrink-0">
              {status.configured && (
                <button
                  type="button"
                  onClick={handleConnect}
                  disabled={connecting}
                  className="px-3 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                >
                  {connecting ? "Apertura..." : status.connected ? "Ricollega" : "Collega Google Drive"}
                </button>
              )}
              {status.connected && (
                <button
                  type="button"
                  onClick={handleDisconnect}
                  className="px-3 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-[11px] font-semibold transition cursor-pointer"
                >
                  Scollega
                </button>
              )}
            </div>
          </div>

          <form key={status.client_id ?? "empty"} onSubmit={handleSave} className="space-y-4">
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
                Client ID
              </label>
              <input
                name="client_id"
                defaultValue={status.client_id ?? ""}
                placeholder="1234567890-abcdefg.apps.googleusercontent.com"
                className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
                Client Secret
              </label>
              <input
                name="client_secret"
                type="password"
                autoComplete="new-password"
                placeholder={status.client_secret_configured ? "•••••••• (già salvato)" : "GOCSPX-..."}
                className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
              />
              <p className="text-[10px] text-slate-500">
                Lascia vuoto per non cambiarlo. Una volta salvato non viene più mostrato.
              </p>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
                ID cartella di destinazione (facoltativo)
              </label>
              <input
                name="parent_folder_id"
                defaultValue={status.parent_folder_id ?? ""}
                placeholder="Vuoto = radice del Drive"
                className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
              />
              <p className="text-[10px] text-slate-500">
                Apri la cartella su Drive e copia la parte finale dell&apos;indirizzo, dopo
                <code className="mx-1">/folders/</code>. Le cartelle dei contratti nasceranno lì dentro.
              </p>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
                URI di reindirizzamento da registrare su Google
              </label>
              <CopyableValue value={status.redirect_uri} />
              <p className="text-[10px] text-slate-500">
                Incollalo tale e quale fra gli <em>Authorized redirect URIs</em> del client OAuth,
                sulla console Google Cloud. Se non combacia carattere per carattere, Google rifiuta
                il collegamento.
              </p>
            </div>

            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
            >
              {saving ? "Salvataggio..." : "Salva"}
            </button>
            {saved && (
              <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
                Credenziali salvate.
              </div>
            )}
          </form>
        </>
      )}

      {error && (
        <div className="mt-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
          {error}
        </div>
      )}
    </div>
  );
}
