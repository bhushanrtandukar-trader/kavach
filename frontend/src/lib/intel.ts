import type { IntelEntry, SiteCheck } from "./api";

export type Level = "low" | "medium" | "high" | "critical";
export type Priority = "critical" | "high" | "medium" | "low";

export const LEVEL: Record<string, { label: string; color: string }> = {
  low: { label: "Low", color: "var(--success)" },
  medium: { label: "Medium", color: "var(--warning)" },
  elevated: { label: "Elevated", color: "var(--warning)" },
  high: { label: "High", color: "var(--danger)" },
  critical: { label: "Critical", color: "var(--danger)" },
};

export const PRIORITY_ORDER: Priority[] = ["critical", "high", "medium", "low"];

export const PRIORITY_TITLE: Record<Priority, string> = {
  critical: "Fix these first",
  high: "Then these",
  medium: "When you have a moment",
  low: "In good shape",
};

/** "Security Risk: 18/100 — Low" */
export function riskText(risk: number, level: string): string {
  return `${risk}/100 — ${LEVEL[level]?.label ?? level}`;
}

export function groupByPriority(entries: IntelEntry[]): { priority: Priority; entries: IntelEntry[] }[] {
  return PRIORITY_ORDER.map((priority) => ({ priority, entries: entries.filter((e) => e.priority === priority) })).filter((g) => g.entries.length > 0);
}

type Decision = { label: string; detail: string; tone: "success" | "warning" | "danger" | "neutral" };
const DECISIONS: Record<string, { label: string; detail: string; tone: "success" | "warning" | "danger" | "neutral" }> = {
  autofill: { label: "Safe to autofill", detail: "Matches a saved login and the address looks clean.", tone: "success" },
  confirm: { label: "Ask before filling", detail: "Matches a saved login, but something looks off.", tone: "warning" },
  block: { label: "Blocked: likely phishing", detail: "Kavach would refuse to fill a password here.", tone: "danger" },
  no_match: { label: "No saved login", detail: "Nothing to fill on this site.", tone: "neutral" },
};

export const CATEGORY_TONE: Record<string, string> = {
  banking: "var(--danger)",
  identity: "var(--danger)",
  cloud: "var(--warning)",
  dev: "var(--primary)",
  work: "var(--accent)",
  social: "var(--muted-foreground)",
  shopping: "var(--muted-foreground)",
  other: "var(--muted-foreground)",
};

const NO_MATCH: Decision = { label: "No saved login", detail: "Nothing to fill on this site.", tone: "neutral" };
export const decisionOf = (d: string): Decision => DECISIONS[d] ?? NO_MATCH;

/** How much of the person's critical accounts have two-factor recorded, e.g. "2 of 5". */
export function mfaCoverage(critical: number, withoutMfa: number): string {
  return critical === 0 ? "n/a" : `${critical - withoutMfa} of ${critical}`;
}
