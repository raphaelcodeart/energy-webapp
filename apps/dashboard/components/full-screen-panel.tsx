"use client";

import { useEffect } from "react";

/** A full-viewport working surface, for the flows that are a task rather
    than a question.

    Activating a contract and finishing one are multi-step jobs -- an
    address, several codes, four or five documents, then a payment plan.
    Those used to run inside a `max-w-lg` dialog, which on a phone meant a
    small scrolling box inside the page behind it, with the document list
    and the payment options each competing for the same few hundred pixels.
    This takes the whole screen instead: one column, one scrollbar, a
    header that stays put so "torna indietro" is always in reach.

    Still a component rather than a route, deliberately: the caller already
    holds the product (or the contract) it was opened from, and a route
    would mean re-fetching and re-authorizing all of it to display the same
    thing one URL later. */
export function FullScreenPanel({
  eyebrow,
  title,
  subtitle,
  onClose,
  children,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
}) {
  // The page underneath must not scroll behind this one -- two scrollbars
  // on a phone is how somebody ends up thinking the form is frozen.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950 light:bg-slate-50 animate-fade-in">
      <div className="sticky top-0 z-10 border-b border-white/10 light:border-slate-200 bg-slate-950/95 light:bg-white/95 backdrop-blur-sm">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 py-3 flex items-center gap-3">
          <button
            onClick={onClose}
            aria-label="Torna indietro"
            className="p-2 -ml-2 rounded-xl hover:bg-white/10 light:hover:bg-slate-900/5 text-slate-400 hover:text-white light:hover:text-slate-900 transition cursor-pointer shrink-0"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="min-w-0 flex-1">
            {eyebrow && (
              <p className="text-[10px] font-semibold text-orange-400 uppercase tracking-wide">{eyebrow}</p>
            )}
            <h2 className="text-base sm:text-lg font-bold text-white light:text-slate-900 truncate">{title}</h2>
          </div>
        </div>
        {subtitle && (
          <div className="mx-auto max-w-3xl px-4 sm:px-6 pb-3 -mt-1">{subtitle}</div>
        )}
      </div>

      {/* The bottom padding is not decoration: on a phone the browser's own
          toolbar overlaps the last few rows of a tall form. */}
      <div className="mx-auto max-w-3xl px-4 sm:px-6 py-6 pb-28">{children}</div>
    </div>
  );
}

/** The numbered "sei qui" strip shared by the activation and completion
    screens. `current` is an index into `steps`; everything before it reads
    as done. */
export function FullScreenSteps({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div className="flex items-center gap-1.5 sm:gap-2">
      {steps.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <div key={label} className="flex items-center gap-1.5 sm:gap-2 min-w-0">
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 ${
                active
                  ? "bg-orange-600 text-white"
                  : done
                    ? "bg-emerald-500/80 text-white"
                    : "bg-white/10 light:bg-slate-900/10 text-slate-400"
              }`}
            >
              {done ? "✓" : i + 1}
            </div>
            <span
              className={`text-[11px] font-semibold truncate ${
                active ? "text-white light:text-slate-900" : "text-slate-500"
              }`}
            >
              {label}
            </span>
            {i < steps.length - 1 && <div className="w-4 sm:w-8 h-px bg-white/10 light:bg-slate-300 shrink-0" />}
          </div>
        );
      })}
    </div>
  );
}
