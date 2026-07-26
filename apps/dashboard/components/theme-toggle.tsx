"use client";

import { useTheme } from "@/lib/theme";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === "light";

  return (
    <button
      onClick={toggleTheme}
      title={isLight ? "Passa alla modalità notte" : "Passa alla modalità giorno"}
      aria-label="Cambia tema"
      className={`relative inline-flex h-9 w-16 shrink-0 items-center rounded-full border transition-colors cursor-pointer ${
        isLight
          ? "bg-slate-200/80 border-slate-300"
          : "bg-slate-800/80 border-white/10"
      } ${className}`}
    >
      <span
        className={`absolute flex h-7 w-7 items-center justify-center rounded-full shadow-md transition-all duration-300 ${
          isLight ? "left-[2px] bg-white text-amber-500" : "left-[calc(100%-1.75rem-2px)] bg-slate-900 text-violet-300"
        }`}
      >
        {isLight ? (
          <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 4.5a1 1 0 011-1v0a1 1 0 01-2 0v0a1 1 0 011 1zm0 15a1 1 0 011 1v0a1 1 0 01-2 0v0a1 1 0 011-1zM4.5 12a1 1 0 01-1 1H3.5a1 1 0 010-2H3.5a1 1 0 011 1zm16 0a1 1 0 011-1h.01a1 1 0 010 2H20.5a1 1 0 01-1-1zM6.34 6.34a1 1 0 010-1.41.01l.01-.01a1 1 0 111.4 1.42l-.7.7a1 1 0 01-1.41-.01l.7-.7zm11.32 11.32a1 1 0 011.41 0l.01.01a1 1 0 01-1.42 1.4l-.7-.7a1 1 0 01.01-1.41l.69.7zM6.34 17.66l-.7.7a1 1 0 11-1.4-1.42l.7-.7a1 1 0 111.4 1.42zM19.07 4.93a1 1 0 010 1.41l-.7.7a1 1 0 01-1.41-1.4l.7-.7a1 1 0 011.41 0z" />
            <circle cx="12" cy="12" r="4.5" />
          </svg>
        ) : (
          <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M21.75 15.5A9.72 9.72 0 0118.5 16 9.75 9.75 0 018.75 6.25c0-1.15.17-2.26.5-3.3a.75.75 0 00-.94-.94A11.25 11.25 0 108.7 21.19a11.25 11.25 0 0013.99-4.75.75.75 0 00-.94-.94z" />
          </svg>
        )}
      </span>
    </button>
  );
}
