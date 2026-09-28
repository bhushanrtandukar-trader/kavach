"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Circle, History } from "lucide-react";
import { motion } from "motion/react";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { cn, formatDateTime, relativeTime } from "@/lib/utils";

const KIND = {
  good: { icon: CheckCircle2, color: "var(--success)" },
  warn: { icon: AlertTriangle, color: "var(--warning)" },
  info: { icon: Circle, color: "var(--muted-foreground)" },
} as const;

/** Your security over time: what improved, what got worse, and when. */
export function SecurityTimeline() {
  const { data, isLoading } = useQuery({ queryKey: ["timeline"], queryFn: api.timeline, staleTime: 10_000 });
  if (isLoading) return <Skeleton className="h-64" />;
  if (!data || data.length === 0) {
    return <EmptyState icon={<History />} title="Your timeline starts here" description="Every scan and every password change is recorded, so you can see your security improve over time." />;
  }
  return (
    <ol className="glass relative rounded-3xl px-6 py-5">
      <span className="absolute bottom-8 left-[2.15rem] top-8 w-px bg-border" aria-hidden />
      {data.map((e, i) => {
        const k = KIND[e.kind as keyof typeof KIND] ?? KIND.info;
        const Icon = k.icon;
        return (
          <motion.li key={`${e.ts}-${i}`} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 10) * 0.04 }} className="relative flex gap-4 py-3">
            <span className="relative z-10 mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-background ring-4 ring-background" style={{ color: k.color }}>
              <Icon className={cn("size-[18px]", e.kind === "info" && "size-3")} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className="font-medium">{e.title}</span>
                <span className="text-xs text-muted-foreground" title={formatDateTime(e.ts)}>{relativeTime(e.ts)}</span>
              </div>
              {e.detail && <p className="text-sm text-muted-foreground">{e.detail}</p>}
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}
