import type { MetadataRoute } from "next";

// Lets a phone add DocIntel to its home screen with the right name and icon (D74).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "DocIntel",
    short_name: "DocIntel",
    description: "Extract, validate and search invoice data from PDFs, images and spreadsheets.",
    start_url: "/",
    display: "standalone",
    background_color: "#0b121d",
    theme_color: "#0b121d",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
