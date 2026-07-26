"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

type Theme = "dark" | "light";

const ThemeContext = createContext<{ theme: Theme; toggleTheme: () => void } | null>(null);

const STORAGE_KEY = "lial-theme";

/**
 * Inline script injected before hydration (see app/layout.tsx) so the correct
 * theme applies on first paint -- without this, the page would flash the
 * wrong theme for a frame while React mounts and reads localStorage.
 */
export const themeInitScript = `
(function () {
  try {
    var stored = localStorage.getItem("${STORAGE_KEY}");
    // Day mode is the product default on first visit -- night mode is an
    // explicit opt-in via the toggle, not inferred from the OS preference.
    var theme = stored === "light" || stored === "dark" ? stored : "light";
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();
`;

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    // Reads the attribute themeInitScript already set before hydration (see
    // app/layout.tsx) so this component's state matches it post-mount.
    // Deliberately NOT a lazy useState initializer: that would run during the
    // render itself and could disagree with the server-rendered HTML (which
    // always assumes "dark", since the server has no access to localStorage),
    // causing a hydration mismatch. Correcting state one tick after mount is
    // the standard, hydration-safe pattern for syncing with this kind of
    // external, pre-hydration DOM mutation.
    const current = document.documentElement.getAttribute("data-theme");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (current === "light" || current === "dark") setTheme(current);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // localStorage unavailable (private browsing, etc.) -- theme just won't persist
      }
      return next;
    });
  }, []);

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
