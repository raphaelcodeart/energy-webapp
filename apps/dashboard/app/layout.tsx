import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";

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
    <html lang="it" className={`${outfit.variable}`}>
      <body className="min-h-screen antialiased bg-[#090d16] text-[#f8fafc]">
        {children}
      </body>
    </html>
  );
}
