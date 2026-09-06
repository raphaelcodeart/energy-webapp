"use client";

import Image from "next/image";

// Small, short, purely decorative themed header images -- lets a user glance
// at the top of a section and immediately recognize "contracts", "customers",
// "network", etc. Never load-bearing content, so a broken/slow image degrades
// silently (the section title below still says what it needs to say).
// All bundled locally (apps/dashboard/public/images/), not hotlinked -- the
// original Wikimedia hotlinks (dim/dark, and "commissions"/"wallets" sharing
// one image) were replaced Session 28 with brighter, more professional
// photos, each section now with its own distinct image.
export const SECTION_IMAGES = {
  energy: "/images/header-energy.jpg",
  customers: "/images/header-customers.jpg",
  network: "/images/header-network.jpg",
  products: "/images/header-products.jpg",
  commissions: "/images/header-commissions.jpg",
  wallets: "/images/header-wallets.jpg",
  support: "/images/header-support.jpg",
  documentation: "/images/documentation-header.jpg",
} as const;

export type SectionImageKey = keyof typeof SECTION_IMAGES;

export function SectionBanner({ image, alt }: { image: SectionImageKey; alt: string }) {
  return (
    <div className="relative h-32 sm:h-44 rounded-2xl overflow-hidden mb-6 border border-white/5 light:border-slate-200">
      <Image src={SECTION_IMAGES[image]} alt={alt} fill priority className="object-cover" sizes="100vw" />
      <div className="absolute inset-0 bg-gradient-to-r from-slate-950/80 via-slate-950/40 to-transparent light:from-white/70 light:via-white/30" />
    </div>
  );
}
