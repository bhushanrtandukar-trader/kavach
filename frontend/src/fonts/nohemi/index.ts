import localFont from "next/font/local";

// Nohemi, self-hosted (see LICENSE.txt in this folder). Weights match what the UI actually uses
// (font-normal/medium/semibold/bold), so next/font/local can pick the right file per weight and font-display
// stays "swap" with no network request at runtime.
export const Nohemi = localFont({
  src: [
    { path: "./Nohemi-Regular.woff2", weight: "400", style: "normal" },
    { path: "./Nohemi-Medium.woff2", weight: "500", style: "normal" },
    { path: "./Nohemi-SemiBold.woff2", weight: "600", style: "normal" },
    { path: "./Nohemi-Bold.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-nohemi",
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "sans-serif"],
});
