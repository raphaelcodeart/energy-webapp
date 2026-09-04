"use client";

// Small, short, purely decorative themed header images -- lets a user glance
// at the top of a section and immediately recognize "contracts", "customers",
// "network", etc. Never load-bearing content, so a broken/slow image degrades
// silently (the section title below still says what it needs to say).
// Sourced from Wikimedia Commons (free, no auth), same method used earlier in
// this project for product photos.
export const SECTION_IMAGES = {
  energy:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Panorama_Kraftwerk_Niederau%C3%9Fem_Neurath_Frimmersdorf_Vollrather_H%C3%B6he.JPG/1920px-Panorama_Kraftwerk_Niederau%C3%9Fem_Neurath_Frimmersdorf_Vollrather_H%C3%B6he.JPG",
  customers:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Middle-aged_businesswoman_typing_on_laptop_at_home_office.jpg/1920px-Middle-aged_businesswoman_typing_on_laptop_at_home_office.jpg",
  network:
    "https://upload.wikimedia.org/wikipedia/commons/6/68/EFTA00002005_-_Server_rack_filled_with_networking_equipment_and_cables_including_blue_Ethernet_connections_and_orange_wires_in_a_data_center_environment.jpg",
  products:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/45/Rooftop_solar_photovoltaic_installation.jpg/1280px-Rooftop_solar_photovoltaic_installation.jpg",
  commissions:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e5/Piggy-bank-968302.jpg/1920px-Piggy-bank-968302.jpg",
  support:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/6/64/Reception_Desk.jpg/1280px-Reception_Desk.jpg",
  // Bundled locally (apps/dashboard/public/images/), not hotlinked -- picked
  // deliberately over a Commons hotlink for this one so it never depends on
  // Wikimedia's availability/URL structure.
  documentation: "/images/documentation-header.jpg",
} as const;

export type SectionImageKey = keyof typeof SECTION_IMAGES;

export function SectionBanner({ image, alt }: { image: SectionImageKey; alt: string }) {
  return (
    <div className="relative h-32 sm:h-44 rounded-2xl overflow-hidden mb-6 border border-white/5 light:border-slate-200">
      {/* eslint-disable-next-line @next/next/no-img-element -- external, unoptimized decorative image; next/image would require remote-pattern config for a source that varies by section */}
      <img src={SECTION_IMAGES[image]} alt={alt} className="w-full h-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-r from-slate-950/80 via-slate-950/40 to-transparent light:from-white/70 light:via-white/30" />
    </div>
  );
}
