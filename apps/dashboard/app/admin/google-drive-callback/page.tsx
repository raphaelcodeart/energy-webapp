"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { friendlyApiError } from "@/lib/api-error";

/** Dove Google rimanda l'amministratore dopo il consenso.

    Questo percorso è anche l'URI esatto che va registrato fra gli
    "Authorized redirect URIs" del client OAuth: lo costruisce il server
    (`integrations/google_drive.py::CALLBACK_PATH`) e lo mostra nelle
    impostazioni, così non c'è da ricopiarlo a memoria.

    La pagina non fa altro che consegnare il `code` al backend, che è l'unico
    a conoscere il client secret. */
function GoogleDriveCallback() {
  const params = useSearchParams();
  const [state, setState] = useState<"working" | "done" | "failed">("working");
  const [message, setMessage] = useState<string | null>(null);
  // React monta due volte in sviluppo (StrictMode), e un authorization code
  // di Google si può spendere UNA sola volta: la seconda tornerebbe
  // "invalid_grant" e mostrerebbe un errore a fronte di un collegamento
  // riuscito.
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;

    const code = params.get("code");
    const oauthState = params.get("state");
    const denied = params.get("error");

    async function run() {
      if (denied) {
        setState("failed");
        setMessage("Autorizzazione annullata su Google.");
        return;
      }
      if (!code || !oauthState) {
        setState("failed");
        setMessage("Google non ha restituito i dati necessari. Riprova dalle impostazioni.");
        return;
      }
      try {
        const res = await fetch("/api/proxy/integrations/google-drive/callback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, state: oauthState }),
        });
        if (!res.ok) throw new Error(await friendlyApiError(res));
        const status = await res.json();
        setMessage(status.account_email ? `Collegato a ${status.account_email}.` : "Collegamento completato.");
        setState("done");
      } catch (err: any) {
        setMessage(err?.message || "Collegamento non riuscito.");
        setState("failed");
      }
    }
    run();
  }, [params]);

  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-slate-950 light:bg-slate-50">
      <div className="w-full max-w-md glass-card rounded-2xl p-8 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white text-center">
        <h1 className="text-lg font-bold text-white light:text-slate-900">
          {state === "working"
            ? "Collegamento a Google Drive…"
            : state === "done"
              ? "Google Drive collegato"
              : "Collegamento non riuscito"}
        </h1>
        {message && (
          <p
            className={`text-sm mt-2 ${
              state === "failed" ? "text-rose-400" : "text-slate-400 light:text-slate-500"
            }`}
          >
            {message}
          </p>
        )}
        {state !== "working" && (
          <>
            <Link
              href="/admin"
              className="inline-block mt-6 px-5 py-2.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition"
            >
              Torna alla dashboard
            </Link>
            <p className="text-[11px] text-slate-500 mt-3">
              Lo stato del collegamento si vede in <strong>Impostazioni</strong>.
            </p>
          </>
        )}
      </div>
    </main>
  );
}

export default function GoogleDriveCallbackPage() {
  return (
    <Suspense fallback={null}>
      <GoogleDriveCallback />
    </Suspense>
  );
}
