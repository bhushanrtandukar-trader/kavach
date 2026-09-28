import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import { Aurora } from "@/components/aurora";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Kavach — Security Intelligence", template: "%s · Kavach" },
  description: "Self-hosted vault and security intelligence for teams: private, explainable, and prioritised.",
  robots: { index: false, follow: false },
  icons: { icon: "/icon.png" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#08080f" },
    { media: "(prefers-color-scheme: light)", color: "#f5f4ff" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body suppressHydrationWarning>
        <Aurora />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
