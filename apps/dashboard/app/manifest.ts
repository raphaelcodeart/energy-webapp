import type { MetadataRoute } from "next";

// Lets "Aggiungi a schermata Home" on Android show the real app icon and
// name instead of a screenshot/generic globe -- icon.png/apple-icon.png
// (same directory) already cover iOS via Next's file-based favicon
// convention; this covers the Android/PWA "manifest" side of the same ask.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Lial Energy",
    short_name: "Lial Energy",
    start_url: "/login",
    display: "standalone",
    background_color: "#090d16",
    theme_color: "#ea580c",
    icons: [
      { src: "/icon.png", sizes: "512x512", type: "image/png" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
