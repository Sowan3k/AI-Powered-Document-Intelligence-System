import type { Metadata, Viewport } from "next";
import "./globals.css";

import { Ambient, Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "DocIntel",
  description: "Extract, validate and search invoice data from PDFs, images and spreadsheets.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eef1f6" },
    { media: "(prefers-color-scheme: dark)", color: "#06070b" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <Ambient />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
