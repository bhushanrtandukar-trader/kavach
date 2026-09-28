import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ───────────────────────── time ─────────────────────────
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31_536_000],
  ["month", 2_592_000],
  ["week", 604_800],
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];
const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** "3 minutes ago", "yesterday", "in 2 hours".  `ts` is epoch seconds, as the API returns. */
export function relativeTime(ts: number | null | undefined, nowMs: number = Date.now()): string {
  if (!ts) return "never";
  const diff = ts - nowMs / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return "just now";
  for (const [unit, secs] of UNITS) {
    if (abs >= secs) return rtf.format(Math.round(diff / secs), unit);
  }
  return rtf.format(Math.round(diff / 60), "minute");
}

export function formatDateTime(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ───────────────────────── names & colours ─────────────────────────
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return (parts[0] ?? "?").slice(0, 2).toUpperCase();
  return ((parts[0]?.[0] ?? "") + (parts[parts.length - 1]?.[0] ?? "")).toUpperCase();
}

function hash(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const GRADIENTS: [string, string][] = [
  ["#6b46ff", "#a855f7"],
  ["#06b6d4", "#3b82f6"],
  ["#10b981", "#06b6d4"],
  ["#f43f5e", "#f97316"],
  ["#f59e0b", "#ef4444"],
  ["#8b5cf6", "#ec4899"],
  ["#0ea5e9", "#6366f1"],
  ["#14b8a6", "#84cc16"],
];

/** A stable gradient per name, so a person or vault always looks the same. */
export function gradientFor(seed: string): string {
  const [a, b] = GRADIENTS[hash(seed.toLowerCase()) % GRADIENTS.length] ?? GRADIENTS[0]!;
  return `linear-gradient(135deg, ${a}, ${b})`;
}

const BRANDS: Record<string, string> = {
  gmail: "#ea4335", google: "#4285f4", github: "#24292e", gitlab: "#fc6d26", facebook: "#1877f2",
  instagram: "#e4405f", twitter: "#1da1f2", linkedin: "#0a66c2", microsoft: "#00a4ef", outlook: "#0078d4",
  apple: "#555555", icloud: "#3478f6", netflix: "#e50914", spotify: "#1db954", youtube: "#ff0000",
  amazon: "#ff9900", aws: "#ff9900", dropbox: "#0061ff", reddit: "#ff4500", discord: "#5865f2",
  slack: "#4a154b", zoom: "#2d8cff", paypal: "#003087", steam: "#1b2838", twitch: "#9146ff",
  whatsapp: "#25d366", telegram: "#229ed9", signal: "#3a76f0", notion: "#191919", figma: "#f24e1e",
  bitbucket: "#0052cc", digitalocean: "#0080ff", heroku: "#430098", vercel: "#111111", netlify: "#00c7b7",
  cloudflare: "#f38020", openai: "#10a37f", anthropic: "#d97757", jenkins: "#d24939", jira: "#0052cc",
  atlassian: "#0052cc", stripe: "#635bff", shopify: "#7ab55c", namecheap: "#de3723", godaddy: "#1bdbdb",
  esewa: "#4caf50", khalti: "#5e2bff", fonepay: "#ff6b00", nabil: "#c8102e", ncell: "#e30613",
};

/** Brand colour for well-known services (matched by substring), else a stable gradient. */
export function serviceStyle(service: string): { background: string } {
  const s = service.toLowerCase();
  const key = Object.keys(BRANDS).find((k) => s.includes(k));
  if (key) {
    const c = BRANDS[key]!;
    return { background: `linear-gradient(135deg, ${c}, color-mix(in oklab, ${c} 70%, black))` };
  }
  return { background: gradientFor(service) };
}

export function serviceLetters(service: string): string {
  const words = service.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return ((words[0]?.[0] ?? "") + (words[1]?.[0] ?? "")).toUpperCase();
  return (words[0]?.[0] ?? "?").toUpperCase();
}

// ───────────────────────── clipboard ─────────────────────────
let clearTimer: ReturnType<typeof setTimeout> | undefined;

/** Copy text and wipe the clipboard afterwards (only if it still holds what we copied). */
export async function copySecret(text: string, clearAfterMs = 30_000): Promise<void> {
  await navigator.clipboard.writeText(text);
  if (clearTimer) clearTimeout(clearTimer);
  clearTimer = setTimeout(async () => {
    try {
      if ((await navigator.clipboard.readText()) === text) await navigator.clipboard.writeText("");
    } catch {
      // Reading the clipboard can be blocked; wiping it blind is the safer failure mode.
      try {
        await navigator.clipboard.writeText("");
      } catch {
        /* nothing more we can do */
      }
    }
  }, clearAfterMs);
}

export async function copyPlain(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

export function plural(n: number, one: string, many = one + "s"): string {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

/**
 * Turn an entry's URL into something safe to link to. Only http(s) is ever clickable: the text is
 * user-supplied, so `javascript:` and `data:` links must never become anchors.
 */
export function safeHost(url: string): { href: string; host: string } | null {
  try {
    const u = new URL(/^[a-z][a-z0-9+.-]*:/i.test(url) ? url : `https://${url}`);
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    return { href: u.href, host: u.hostname.replace(/^www\./, "") };
  } catch {
    return null;
  }
}
