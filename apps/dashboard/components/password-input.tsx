"use client";

import { useState } from "react";

type PasswordInputProps = React.InputHTMLAttributes<HTMLInputElement>;

/** Drop-in replacement for a plain <input type="password"> that adds a
    click-to-reveal eye toggle -- hidden by default, independently
    toggleable per instance (a "Password" field and a "Ripeti Password"
    field next to it each keep their own show/hide state). Every other prop
    (value, onChange, required, minLength, placeholder, autoComplete,
    id, className...) passes straight through, so it drops into any
    existing form without touching layout, validation, or the caller's own
    state -- see login/page.tsx, r/[code]/page.tsx, reset-password/page.tsx,
    and admin-organization-settings-panel.tsx for call sites.

    The extra right padding for the icon is set via inline `style` (not a
    `pr-*` Tailwind class appended to the caller's `className`) so it can
    never lose a specificity fight against whatever `px-*`/`pr-*` class the
    caller already passed -- inline style always wins, regardless of
    stylesheet rule order. */
export function PasswordInput({ className, style, ...props }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative">
      <input
        {...props}
        type={visible ? "text" : "password"}
        className={className}
        style={{ paddingRight: "2.25rem", ...style }}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Nascondi password" : "Mostra password"}
        aria-pressed={visible}
        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-slate-400 hover:text-slate-200 light:text-slate-500 light:hover:text-slate-700 transition cursor-pointer"
      >
        {visible ? (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
          </svg>
        ) : (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        )}
      </button>
    </div>
  );
}
