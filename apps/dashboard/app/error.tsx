"use client";

import { useEffect } from "react";

/** Root error boundary -- without this, ANY uncaught client-side exception
    anywhere in the app (a bad API shape, a null a modal didn't expect, ...)
    unmounts the whole page silently: no error.tsx existed before this, so
    Next's default fallback left just the app's own dark background visible,
    with no button and no indication anything had gone wrong ("the screen
    goes dark and nothing opens"). This makes a crash visible and
    recoverable instead of a silent dead end. */
export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-md w-full glass-card rounded-2xl p-8 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white text-center">
        <svg className="w-12 h-12 text-rose-400 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h1 className="text-lg font-bold text-white light:text-slate-900 mb-2">Qualcosa è andato storto</h1>
        <p className="text-sm text-slate-400 light:text-slate-500 mb-6">
          Si è verificato un errore imprevisto in questa schermata. Riprova -- se il problema
          persiste, contatta l&apos;assistenza tecnica.
        </p>
        <button
          onClick={reset}
          className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-sm font-semibold text-white shadow-lg transition cursor-pointer"
        >
          Riprova
        </button>
      </div>
    </div>
  );
}
