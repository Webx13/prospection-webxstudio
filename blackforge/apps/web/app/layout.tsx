import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { defaultLocale, getMessages } from "@/lib/i18n";

import "./globals.css";

const t = getMessages();

export const metadata: Metadata = {
  title: { default: t.brand.name, template: `%s · ${t.brand.name}` },
  description: t.brand.tagline,
  // Produit non lancé : pas d'indexation tant que la publication n'est pas décidée.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  colorScheme: "dark",
  themeColor: "#07070a",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang={defaultLocale} className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
