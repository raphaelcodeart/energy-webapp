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

export function SectionBanner({
  image, alt, compact = false, children,
}: {
  image: SectionImageKey;
  alt: string;
  /** Shorter hero, used on the customer/promoter dashboard home so the
      photo stays present but doesn't push the actually useful content
      (wallet balance, shortcuts) below the fold -- see
      dashboard-wallet-stats.tsx and customer/promoter-client-page.tsx. */
  compact?: boolean;
  /** Overlaid on top of the photo (greeting text, shortcuts) -- only
      meaningful together with `compact`; a full-size banner elsewhere
      stays purely decorative, no children passed. */
  children?: React.ReactNode;
}) {
  return (
    <div
      className={`relative rounded-2xl overflow-hidden mb-6 border border-white/5 light:border-slate-200 ${
        compact ? "min-h-[92px] sm:min-h-[104px]" : "h-32 sm:h-44"
      }`}
    >
      <Image src={SECTION_IMAGES[image]} alt={alt} fill priority className="object-cover" sizes="100vw" />
      <div
        className={`absolute inset-0 ${
          compact
            ? "bg-gradient-to-r from-slate-950/90 via-slate-950/75 to-slate-950/50 light:from-white/90 light:via-white/75 light:to-white/50"
            : "bg-gradient-to-r from-slate-950/80 via-slate-950/40 to-transparent light:from-white/70 light:via-white/30"
        }`}
      />
      {children && <div className="relative z-10 h-full flex items-center px-5 py-4 sm:px-6">{children}</div>}
    </div>
  );
}
