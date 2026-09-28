"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, CalendarClock, Copy, GitCompareArrows, HeartPulse, ShieldAlert, ShieldCheck, Wrench } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { HealthRing } from "@/components/health-ring";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/controls";
import { Avatar, Badge, EmptyState, Skeleton } from "@/components/ui/misc";
import { useVault } from "@/components/vault-context";
import { api, ApiError, type HealthReport } from "@/lib/api";
import { setPendingOpen } from "@/lib/events";
import { cn, serviceLetters, serviceStyle } from "@/lib/utils";

type Kind = "breached" | "reused" | "weak" | "similar" | "old";

const KINDS: { kind: Kind; title: string; help: string; icon: React.ComponentType<{ className?: string }>; tone: string }[] = [
  { kind: "breached", title: "In data breaches", help: "Seen in public leaks", icon: AlertOctagon, tone: "var(--danger)" },
  { kind: "reused", title: "Reused", help: "Same password, several places", icon: Copy, tone: "var(--danger)" },
  { kind: "weak", title: "Weak", help: "Easy to guess", icon: ShieldAlert, tone: "var(--warning)" },
  { kind: "similar", title: "Near-duplicates", help: "Tiny variations of each other", icon: GitCompareArrows, tone: "var(--warning)" },
  { kind: "old", title: "Stale", help: "Unchanged for 180+ days", icon: CalendarClock, tone: "var(--muted-foreground)" },
];

export default function HealthPage() {
  const router = useRouter();
  const { vault, vaultId, select } = useVault();
  const [scope, setScope] = useState<"this" | "all">("all");
  const [breach, setBreach] = useState(false);
  const [filter, setFilter] = useState<Kind | null>(null);

  const report = useQuery<HealthReport, ApiError>({
    queryKey: ["health", scope, scope === "this" ? vaultId : null, breach],
    queryFn: () => api.health(scope === "this" ? vaultId : null, breach),
    enabled: scope === "all" || !!vaultId,
    staleTime: 0,
    gcTime: 30_000,
    placeholderData: (p) => p,
  });
  const data = report.data;

  const visible = (data?.entries ?? []).filter((e) => !filter || e.issues.some((i) => i.kind === filter));

  function fix(vaultId: string, entryId: string) {
    select(vaultId);
    setPendingOpen({ vaultId, entryId });
    router.push("/vaults");
  }

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Vault health"
        description="A private check-up of the passwords you can read. It runs on the server; no password is ever shown or sent anywhere."
        actions={
          <div className="glass flex rounded-xl p-1 text-sm">
            {(
              [
                ["all", "All my vaults"],
                ["this", vault?.kind === "personal" ? "Personal only" : (vault?.name ?? "This vault")],
              ] as const
            ).map(([v, label]) => (
              <button key={v} onClick={() => setScope(v)} className={cn("relative max-w-44 truncate rounded-lg px-3.5 py-1.5 font-medium transition-colors", scope === v ? "text-foreground" : "text-muted-foreground hover:text-foreground")}>
                {scope === v && <motion.span layoutId="scope-pill" className="absolute inset-0 rounded-lg bg-primary/15 ring-1 ring-primary/30" />}
                <span className="relative">{label}</span>
              </button>
            ))}
          </div>
        }
      />

      {report.isLoading && !data ? (
        <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      ) : report.isError ? (
        <EmptyState icon={<HeartPulse />} title="Couldn't run the check" description={report.error.message} action={<Button onClick={() => report.refetch()}>Try again</Button>} />
      ) : data && data.total === 0 ? (
        <EmptyState icon={<HeartPulse />} title="Nothing to check yet" description="Add a few logins and come back: this page will tell you which ones to fix first." />
      ) : data ? (
        <>
          <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
            <div className="glass flex flex-col items-center rounded-3xl p-6">
              <HealthRing score={data.score} label={data.label} color={data.color} />
              <div className="mt-4 text-center text-sm text-muted-foreground">{data.total.toLocaleString()} passwords analysed</div>
              <div className="mt-5 w-full space-y-3 border-t pt-4">
                <label className={cn("flex items-start justify-between gap-3 text-sm", !data.breach_allowed && "opacity-60")}>
                  <span>
                    <span className="block font-medium">Check known data breaches</span>
                    <span className="block text-xs text-muted-foreground">
                      {data.breach_allowed ? "Sends only a 5-character hash prefix to haveibeenpwned.com." : "Turned off by your administrator."}
                    </span>
                  </span>
                  <Switch checked={breach} disabled={!data.breach_allowed} onCheckedChange={setBreach} />
                </label>
                {data.note && <p className="rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">{data.note}</p>}
              </div>
            </div>

            <div className="grid content-start gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {KINDS.filter((k) => k.kind !== "breached" || data.breach_checked).map(({ kind, title, help, icon: Icon, tone }, i) => {
                const n = (data.counts as Record<string, number>)[kind] ?? 0;
                const active = filter === kind;
                return (
                  <motion.button
                    key={kind}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.08 * i }}
                    onClick={() => setFilter(active ? null : kind)}
                    disabled={n === 0}
                    className={cn("glass group relative overflow-hidden rounded-2xl p-4 text-left transition-all enabled:hover:-translate-y-0.5 enabled:hover:shadow-lg", active && "ring-2 ring-primary", n === 0 && "opacity-60")}
                  >
                    <div className="absolute -right-6 -top-6 size-24 rounded-full opacity-20 blur-2xl" style={{ background: n ? tone : "transparent" }} />
                    <div className="relative flex items-start justify-between">
                      <span className="flex size-10 items-center justify-center rounded-xl" style={{ background: `color-mix(in oklab, ${tone} 16%, transparent)`, color: tone }}>
                        <Icon className="size-5" />
                      </span>
                      <span className="text-3xl font-semibold tabular-nums">{n}</span>
                    </div>
                    <div className="relative mt-3 font-medium">{title}</div>
                    <div className="relative text-xs text-muted-foreground">{help}</div>
                  </motion.button>
                );
              })}
            </div>
          </div>

          <div className="mt-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold tracking-tight">
                {data.entries.length === 0 ? "All clear" : filter ? `${KINDS.find((k) => k.kind === filter)?.title}` : "Fix these first"}
              </h2>
              {filter && (
                <Button variant="ghost" size="sm" onClick={() => setFilter(null)}>
                  Show all issues
                </Button>
              )}
            </div>
            {data.entries.length === 0 ? (
              <div className="glass flex items-center gap-4 rounded-3xl p-6">
                <span className="flex size-12 items-center justify-center rounded-2xl bg-success/15 text-success">
                  <ShieldCheck className="size-6" />
                </span>
                <div>
                  <div className="font-medium">No weak, reused or stale passwords found.</div>
                  <div className="text-sm text-muted-foreground">Keep it that way: run this check whenever you add a batch of logins.</div>
                </div>
              </div>
            ) : (
              <ul className="glass divide-y overflow-hidden rounded-3xl">
                <AnimatePresence initial={false}>
                  {visible.map((e) => (
                    <motion.li key={e.ref.id} layout="position" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-wrap items-center gap-4 px-4 py-3.5 hover:bg-muted/50">
                      <Avatar name={e.ref.service} gradient={serviceStyle(e.ref.service).background} className="size-10">
                        {serviceLetters(e.ref.service)}
                      </Avatar>
                      <div className="min-w-0 flex-1 basis-56">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{e.ref.service}</span>
                          <span className="text-xs text-muted-foreground">in {e.ref.vault}</span>
                        </div>
                        <ul className="mt-1 space-y-0.5">
                          {e.issues.map((i, k) => (
                            <li key={k} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                              <Badge tone={i.kind === "breached" || i.kind === "reused" ? "danger" : i.kind === "old" ? "neutral" : "warning"} className="mt-px shrink-0">
                                {i.kind}
                              </Badge>
                              <span>{i.detail}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div className="flex w-24 shrink-0 flex-col items-end gap-2">
                        <span className={cn("text-xs font-semibold tabular-nums", e.health < 40 ? "text-danger" : e.health < 70 ? "text-warning" : "text-success")}>{e.health}/100</span>
                        <Button size="sm" variant="secondary" onClick={() => fix(e.ref.vault_id, e.ref.id)}>
                          <Wrench /> Fix
                        </Button>
                      </div>
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ul>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
