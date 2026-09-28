"use client";

import { motion } from "motion/react";
import { Wrench } from "lucide-react";
import { Avatar, Badge } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import type { IntelEntry, IntelRef } from "@/lib/api";
import { CATEGORY_TONE, LEVEL, riskText } from "@/lib/intel";
import { cn, serviceLetters, serviceStyle } from "@/lib/utils";

/** A 0-100 bar that fills in and takes the colour of the risk level. */
export function RiskBar({ risk, level, className }: { risk: number; level: string; className?: string }) {
  const color = LEVEL[level]?.color ?? "var(--muted-foreground)";
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", className)} role="meter" aria-valuenow={risk} aria-valuemin={0} aria-valuemax={100} aria-label="Risk">
      <motion.div className="h-full rounded-full" style={{ background: color }} initial={{ width: 0 }} animate={{ width: `${Math.max(3, risk)}%` }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} />
    </div>
  );
}

export function ServiceAvatar({ service, className }: { service: string; className?: string }) {
  return (
    <Avatar name={service} gradient={serviceStyle(service).background} className={className}>
      {serviceLetters(service)}
    </Avatar>
  );
}

const VALUE: Record<string, string> = { critical: "critical-value account", high: "high-value account", medium: "medium-value account", low: "low-value account" };

export function EntryRiskCard({ entry, onFix, compact }: { entry: IntelEntry; onFix?: (ref: IntelRef) => void; compact?: boolean }) {
  const color = LEVEL[entry.level]?.color ?? "var(--muted-foreground)";
  const issues = entry.factors.filter((f) => f.code !== "strength" || f.p >= 0.16);
  return (
    <div className={cn("flex gap-4", compact ? "" : "px-5 py-4")}>
      <ServiceAvatar service={entry.ref.service} className="mt-0.5 size-11" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <span className="font-semibold">{entry.ref.service}</span>
          <span className="text-xs text-muted-foreground">in {entry.ref.vault}</span>
          <Badge tone="outline" className="normal-case tracking-normal" style={{ color: CATEGORY_TONE[entry.category] }}>
            {entry.category_label}
          </Badge>
          <span className="text-xs text-muted-foreground" title="How much it would hurt if this account were taken over. Priority = likelihood × this.">
            · {VALUE[entry.importance] ?? "account"}
          </span>
          {entry.mfa && <Badge tone="success">2FA</Badge>}
        </div>
        <div className="mt-2 flex items-center gap-3">
          <RiskBar risk={entry.risk} level={entry.level} className="max-w-56" />
          <span className="text-xs font-semibold tabular-nums" style={{ color }}>
            Risk {riskText(entry.risk, entry.level)}
          </span>
        </div>
        <p className="mt-2 text-sm">{entry.headline}</p>
        {entry.advice && <p className="mt-1 text-sm text-muted-foreground">{entry.advice}</p>}
        {issues.length > 0 && (
          <ul className="mt-2.5 flex flex-wrap gap-1.5">
            {issues.map((f) => (
              <li key={f.code} title={f.detail} className="rounded-full border px-2.5 py-0.5 text-[11px] text-muted-foreground">
                {f.label}
              </li>
            ))}
          </ul>
        )}
      </div>
      {onFix && entry.priority !== "low" && (
        <Button size="sm" variant="secondary" className="shrink-0 self-start" onClick={() => onFix(entry.ref)}>
          <Wrench /> Fix
        </Button>
      )}
    </div>
  );
}
