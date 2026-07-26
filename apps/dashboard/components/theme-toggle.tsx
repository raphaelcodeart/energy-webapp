"use client";

import { useTheme } from "@/lib/theme";

const SUN_PATH =
  "M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM18.894 6.166a.75.75 0 00-1.06-1.06l-1.591 1.59a.75.75 0 101.06 1.061l1.591-1.59zM21.75 12a.75.75 0 01-.75.75h-2.25a.75.75 0 010-1.5H21a.75.75 0 01.75.75zM17.834 18.894a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 10-1.061 1.06l1.59 1.591zM12 18a.75.75 0 01.75.75V21a.75.75 0 01-1.5 0v-2.25A.75.75 0 0112 18zM7.758 17.303a.75.75 0 00-1.061-1.06l-1.591 1.59a.75.75 0 001.06 1.061l1.591-1.59zM6 12a.75.75 0 01-.75.75H3a.75.75 0 010-1.5h2.25A.75.75 0 016 12zM6.697 7.757a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 00-1.061 1.06l1.59 1.591z";

const MOON_PATH =
  "M9.528 1.718a.75.75 0 01.162.819A8.97 8.97 0 009 6a9 9 0 009 9 8.97 8.97 0 003.463-.69.75.75 0 01.981.98 10.503 10.503 0 01-9.694 6.46c-5.799 0-10.5-4.7-10.5-10.5 0-4.368 2.667-8.112 6.46-9.694a.75.75 0 01.818.162z";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === "light";

  return (
    <button
      onClick={toggleTheme}
      title={isLight ? "Passa alla modalità notte" : "Passa alla modalità giorno"}
      aria-label={isLight ? "Passa alla modalità notte" : "Passa alla modalità giorno"}
      aria-pressed={!isLight}
      className={`group relative inline-flex h-10 w-[4.5rem] shrink-0 items-center rounded-full border transition-all duration-300 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ${
        isLight
          ? "bg-gradient-to-r from-amber-100 to-sky-100 border-amber-200 shadow-inner"
          : "bg-gradient-to-r from-slate-800 to-indigo-950 border-white/10 shadow-inner"
      } ${className}`}
    >
      {/* Faint context glyphs at each end of the track */}
      <svg
        className={`absolute left-2 h-3.5 w-3.5 transition-opacity ${isLight ? "opacity-0" : "opacity-40 text-slate-400"}`}
        fill="currentColor"
        viewBox="0 0 24 24"
      >
        <path fillRule="evenodd" clipRule="evenodd" d={SUN_PATH} />
      </svg>
      <svg
        className={`absolute right-2 h-3.5 w-3.5 transition-opacity ${isLight ? "opacity-40 text-slate-400" : "opacity-0"}`}
        fill="currentColor"
        viewBox="0 0 24 24"
      >
        <path fillRule="evenodd" clipRule="evenodd" d={MOON_PATH} />
      </svg>

      {/* Sliding knob -- solid glyph reads clearly at this size, unlike a thin outline icon */}
      <span
        className={`absolute flex h-8 w-8 items-center justify-center rounded-full shadow-lg ring-1 transition-all duration-300 ease-out ${
          isLight
            ? "left-1 bg-gradient-to-br from-amber-300 to-amber-500 text-white ring-amber-300/50"
            : "left-[calc(100%-2.25rem)] bg-gradient-to-br from-indigo-500 to-violet-600 text-white ring-violet-400/50"
        }`}
      >
        <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
          <path fillRule="evenodd" clipRule="evenodd" d={isLight ? SUN_PATH : MOON_PATH} />
        </svg>
      </span>
    </button>
  );
}
