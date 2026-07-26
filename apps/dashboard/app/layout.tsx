import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";
import { AppProviders } from "@/app/providers";
import { themeInitScript } from "@/lib/theme";

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Lial Energy Platform",
  description: "Gestionale Lial Energy",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" className={`${outfit.variable}`} data-theme="dark" suppressHydrationWarning>
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
