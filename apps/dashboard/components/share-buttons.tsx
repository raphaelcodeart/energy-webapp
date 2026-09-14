"use client";

import { useState } from "react";
import { type ShareResult, shareOrCopyLink } from "@/lib/share-link";

/** Explicit per-app share buttons, plus the copy-link button.
 *
 * The native share sheet (`navigator.share`) is still here as "Altro", but it
 * is no longer the only option: on a desktop browser it does not exist at
 * all, and even on a phone it costs an extra tap before the person sees
 * WhatsApp. A promoter shares the same link dozens of times a day, so the
 * app they actually use is one tap away.
 *
 * Every destination is a plain link, not a script: no SDK, no tracking
 * pixel, no third-party bundle. The target app opens with the message and
 * the URL already filled in, and the person only has to pick the recipient.
 */

type ShareTarget = {
  key: string;
  label: string;
  /** Built per-destination: WhatsApp takes one combined `text`, Telegram
      takes `url` and `text` separately, mail takes a subject and a body. */
  href: (url: string, text: string, title: string) => string;
  className: string;
  icon: React.ReactNode;
  /** SMS only makes sense where there is a SIM. Hidden on a mouse-driven
      device with a CSS media query rather than a JS check, so there is no
      hydration mismatch and no state to keep. */
  touchOnly?: boolean;
};

const TARGETS: ShareTarget[] = [
  {
    key: "whatsapp",
    label: "WhatsApp",
    href: (url, text) => `https://wa.me/?text=${encodeURIComponent(`${text} ${url}`)}`,
    className: "bg-[#25D366]/10 text-[#25D366] border-[#25D366]/30 hover:bg-[#25D366]/20",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893A11.821 11.821 0 0020.465 3.488" />
      </svg>
    ),
  },
  {
    key: "telegram",
    label: "Telegram",
    href: (url, text) =>
      `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`,
    className: "bg-[#229ED9]/10 text-[#229ED9] border-[#229ED9]/30 hover:bg-[#229ED9]/20",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
      </svg>
    ),
  },
  {
    key: "sms",
    label: "SMS",
    // "?&body=" rather than "?body=" or "&body=": iOS and Android disagree on
    // the separator and this form is the one both accept.
    href: (url, text) => `sms:?&body=${encodeURIComponent(`${text} ${url}`)}`,
    className:
      "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20",
    touchOnly: true,
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
  {
    key: "email",
    label: "Email",
    href: (url, text, title) =>
      `mailto:?subject=${encodeURIComponent(title)}&body=${encodeURIComponent(`${text}\n\n${url}`)}`,
    className: "bg-sky-500/10 text-sky-400 border-sky-500/30 hover:bg-sky-500/20",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  },
];

export function ShareButtons({
  url,
  text,
  title = "Lial Energy",
  className = "",
  hideLabelsOnMobile = false,
}: {
  url: string;
  /** The message that goes with the link, e.g. "Iscriviti con il mio link:". */
  text: string;
  title?: string;
  className?: string;
  /** Icons only on a narrow screen, icons + words from `sm` up. For the
      promoter header, which is on every page of that dashboard: six labelled
      pills would wrap onto three lines there and push the actual content
      down on a phone. Everywhere with room keeps the words. */
  hideLabelsOnMobile?: boolean;
}) {
  const [result, setResult] = useState<ShareResult | null>(null);

  async function handleCopy() {
    const outcome = await shareOrCopyLink({ url, title, text, preferClipboard: true });
    setResult(outcome);
    setTimeout(() => setResult(null), 2000);
  }

  async function handleNative() {
    const outcome = await shareOrCopyLink({ url, title, text });
    setResult(outcome);
    setTimeout(() => setResult(null), 2000);
  }

  const pill = `inline-flex items-center gap-1.5 ${
    hideLabelsOnMobile ? "px-2.5 sm:px-3" : "px-3"
  } py-2 rounded-xl border text-xs font-semibold transition cursor-pointer`;
  // The label is hidden, never removed: a screen reader and a long-press
  // tooltip still get the name of the destination.
  const labelClass = hideLabelsOnMobile ? "hidden sm:inline" : "";

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      {TARGETS.map((target) => (
        <a
          key={target.key}
          href={target.href(url, text, title)}
          target="_blank"
          rel="noopener noreferrer"
          title={target.label}
          aria-label={target.label}
          className={`${pill} ${target.className} ${target.touchOnly ? "hidden [@media(pointer:coarse)]:inline-flex" : ""}`}
        >
          {target.icon}
          <span className={labelClass}>{target.label}</span>
        </a>
      ))}

      {/* The phone's own share sheet -- everything not listed above (Messenger,
          Signal, AirDrop, a notes app...). On desktop it falls back to a copy,
          which is why the label stays neutral. */}
      <button
        onClick={handleNative}
        className={`${pill} bg-white/5 light:bg-slate-900/5 text-slate-300 light:text-slate-600 border-white/10 light:border-slate-300 hover:bg-white/10 hidden [@media(pointer:coarse)]:inline-flex`}
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342a4 4 0 010-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a4 4 0 105.367-5.925 4 4 0 00-5.367 5.925zm0 8.658a4 4 0 105.367 5.925 4 4 0 00-5.367-5.925z" />
        </svg>
        <span className={labelClass}>Altro</span>
      </button>

      <button
        onClick={handleCopy}
        className={`${pill} bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-white border-transparent shadow-lg shadow-orange-500/20`}
      >
        {result === "copied" || result === "shared" ? (
          <>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
            <span className={labelClass}>Link copiato!</span>
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
            </svg>
            <span className={labelClass}>Copia link</span>
          </>
        )}
      </button>
    </div>
  );
}

/** The same options behind one button, for places with no room for a row of
 *  them -- a product card in a grid, the promoter header bar. */
export function ShareMenu({
  url,
  text,
  title = "Lial Energy",
  label = "Condividi",
  buttonClassName = "",
  heading,
}: {
  url: string;
  text: string;
  title?: string;
  label?: string;
  buttonClassName?: string;
  heading?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button onClick={() => setOpen(true)} className={buttonClassName}>
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342a4 4 0 010-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a4 4 0 105.367-5.925 4 4 0 00-5.367 5.925zm0 8.658a4 4 0 105.367 5.925 4 4 0 00-5.367-5.925z" />
        </svg>
        {label}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-sm glass-card rounded-2xl p-5 animate-scale-up"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-semibold text-white light:text-slate-900 mb-1">
              {heading ?? "Condividi il link"}
            </h3>
            <p className="text-[11px] text-slate-500 mb-4 break-all font-mono">{url}</p>
            <ShareButtons url={url} text={text} title={title} />
            <button
              onClick={() => setOpen(false)}
              className="w-full mt-4 text-xs text-slate-500 hover:text-slate-300 transition cursor-pointer"
            >
              Chiudi
            </button>
          </div>
        </div>
      )}
    </>
  );
}
