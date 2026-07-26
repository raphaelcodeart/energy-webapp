import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppProviders } from "@/app/providers";
import { themeInitScript } from "@/lib/theme";

// Inter over the previous Outfit: a standard, professional typeface built for
// admin/dashboard UIs (used by GitHub, Linear, Vercel), instead of Outfit's
// more decorative/geometric look.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Lial Energy Platform",
  description: "Gestionale Lial Energy",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" className={`${inter.variable}`} data-theme="light" suppressHydrationWarning>
      <head>
        {/* Runs before hydration so the stored/system theme applies on first
            paint -- prevents a flash of the wrong theme. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-screen antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
