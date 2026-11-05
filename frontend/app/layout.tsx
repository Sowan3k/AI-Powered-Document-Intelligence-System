import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";

import { Ambient, Providers } from "@/components/providers";

// Type (D80): IBM Plex Sans for text (its digits are all one width, so amounts
// line up), Barlow Semi Condensed for headings and figures, IBM Plex Mono for
// invoice numbers. Served from the app itself, so the strict CSP stays as is.
const plex = localFont({
  src: "./fonts/ibm-plex-sans-latin-wght-normal.woff2",
  variable: "--font-plex",
  weight: "100 700",
  display: "swap",
});
const barlow = localFont({
  src: [
    { path: "./fonts/barlow-semi-condensed-latin-600-normal.woff2", weight: "600" },
    { path: "./fonts/barlow-semi-condensed-latin-700-normal.woff2", weight: "700" },
  ],
  variable: "--font-barlow",
  display: "swap",
});
const plexMono = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-latin-400-normal.woff2", weight: "400" },
    { path: "./fonts/ibm-plex-mono-latin-500-normal.woff2", weight: "500" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "DocIntel",
  description: "Extract, validate and search invoice data from PDFs, images and spreadsheets.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3efe6" },
    { media: "(prefers-color-scheme: dark)", color: "#0b121d" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plex.variable} ${barlow.variable} ${plexMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <Ambient />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
