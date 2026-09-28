"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, CalendarClock, CheckCircle2, ChevronDown, Copy, GitCompareArrows, Lock, ShieldCheck, ShieldOff, Sparkles, Wrench } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { HealthRing } from "@/components/health-ring";
import { PageHeader } from "@/components/page-header";
import { Advisor } from "@/components/security/advisor";
import { EntryRiskCard, ServiceAvatar } from "@/components/security/parts";
import { SiteCheckPanel } from "@/components/security/site-check";
import { SecurityTimeline } from "@/components/security/timeline";
import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/controls";
import { Badge, EmptyState, Skeleton } from "@/components/ui/misc";
import { useVault } from "@/components/vault-context";
import { api, ApiError, type IntelRef, type IntelReport } from "@/lib/api";
import { setPendingOpen } from "@/lib/events";
import { groupByPriority, mfaCoverage, PRIORITY_TITLE } from "@/lib/intel";
import { cn } from "@/lib/utils";

type Tab = "priorities" | "families" | "timeline" | "advisor" | "site";

function Stat({ icon: Icon, label, value, help, tone, delay }: { icon: React.ComponentType<{ className?: string }>; label: string; value: React.ReactNode; help: string; tone: string; delay: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }} className="glass relative overflow-hidden rounded-2xl p-4">
      <div className="absolute -right-6 -top-6 size-24 rounded-full opacity-15 blur-2xl" style={{ background: tone }} />
      <div className="relative flex items-start justify-between">
        <span className="flex size-10 items-center justify-center rounded-xl" style={{ background: `color-mix(in oklab, ${tone} 16%, transparent)`, color: tone }}>
          <Icon className="size-5" />
        </span>
        <span className="text-3xl font-semibold tabular-nums">{value}</span>
      </div>
      <div className="relative mt-3 font-medium">{label}</div>
      <div className="relative text-xs text-muted-foreground">{help}</div>
    </motion.div>
  );
}

function TopActions({ report, onFix }: { report: IntelReport; onFix: (r: IntelRef) => void }) {
  const acts = report.actions.slice(0, 3);
  if (acts.length === 0) {
    return (
      <div className="glass flex items-center gap-4 rounded-3xl p-6">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-success/15 text-success"><CheckCircle2 className="size-6" /></span>
        <div>
          <div className="font-medium">Nothing needs your attention.</div>
          <div className="text-sm text-muted-foreground">Run this check again after you add a batch of logins.</div>
        </div>
      </div>
    );
  }
  const total = acts.reduce((a, b) => a + b.gain, 0);
  return (
    <div className="glass rounded-3xl p-5">
      <div className="mb-3 flex items-center gap-2.5">
        <span className="gradient-bg flex size-9 items-center justify-center rounded-xl text-white"><Sparkles className="size-[18px]" /></span>
        <div>
          <h3 className="font-semibold tracking-tight">{acts.length} action{acts.length === 1 ? "" : "s"} will improve your security the most</h3>
          <p className="text-xs text-muted-foreground">About +{Math.round(total)} points together</p>
        </div>
      </div>
      <ol className="space-y-2">
        {acts.map((a, i) => (
          <motion.li key={a.title} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + i * 0.08 }} className="flex items-center gap-3 rounded-2xl bg-muted/60 p-3">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-background text-xs font-bold">{i + 1}</span>
            <ServiceAvatar service={a.ref.service} className="size-9" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{a.title}</div>
              <div className="line-clamp-2 text-xs text-muted-foreground">{a.why}</div>
            </div>
            <Badge tone="success" className="shrink-0 normal-case tracking-normal">+{a.gain}</Badge>
            <Button size="sm" variant="secondary" onClick={() => onFix(a.ref)}><Wrench /> Fix</Button>
          </motion.li>
        ))}
      </ol>
    </div>
  );
}

export default function SecurityPage() {
  const router = useRouter();
  const { select } = useVault();
  const [tab, setTab] = useState<Tab>("priorities");
  const [breach, setBreach] = useState(false);
  const [showLow, setShowLow] = useState(false);

  const q = useQuery<IntelReport, ApiError>({ queryKey: ["intel", breach], queryFn: () => api.intel(breach, false), staleTime: 0, placeholderData: (p) => p });
  const report = q.data;

  function open(ref: IntelRef) {
    select(ref.vault_id);
    setPendingOpen({ vaultId: ref.vault_id, entryId: ref.id });
    router.push("/vaults");
  }

  const s = report?.summary;
  const groups = report ? groupByPriority(report.entries) : [];

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Security intelligence"
        description="What to fix first, why it matters, and how you're improving. Computed privately on this server: no password is shown, stored or sent anywhere."
      />

      {q.isLoading && !report ? (
        <div className="grid gap-5 lg:grid-cols-[320px_1fr]"><Skeleton className="h-80" /><Skeleton className="h-80" /></div>
      ) : q.isError ? (
        <EmptyState icon={<ShieldOff />} title="Couldn't run the analysis" description={q.error.message} action={<Button onClick={() => q.refetch()}>Try again</Button>} />
      ) : report && report.total === 0 ? (
        <>
          <EmptyState icon={<ShieldCheck />} title="Nothing to analyse yet" description="Add a few logins and this page will tell you which to fix first, and why." />
          <div className="mt-2"><SiteCheckPanel examples={["paypa1.com/login", "github.com", "http://192.168.1.10/admin"]} /></div>
        </>
      ) : report && s ? (
        <>
          <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
            <div className="glass flex flex-col items-center rounded-3xl p-6">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Your security</div>
              <HealthRing score={report.score} label={report.label} color={report.color} />
              <div className="mt-3 text-center text-sm text-muted-foreground">
                {s.accounts} accounts · {s.strong} strong &amp; unique
              </div>
              <div className="mt-5 w-full space-y-3 border-t pt-4">
                <label className={cn("flex items-start justify-between gap-3 text-sm", !report.breach_allowed && "opacity-60")}>
                  <span>
                    <span className="block font-medium">Check known data breaches</span>
                    <span className="block text-xs text-muted-foreground">
                      {report.breach_allowed ? "Sends only a 5-character hash prefix to haveibeenpwned.com." : "Turned off by your administrator."}
                    </span>
                  </span>
                  <Switch checked={breach} disabled={!report.breach_allowed} onCheckedChange={setBreach} />
                </label>
                {report.note && <p className="rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">{report.note}</p>}
              </div>
            </div>

            <div className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <Stat icon={Copy} label="Reused" value={s.reused} help="Identical password elsewhere" tone="var(--danger)" delay={0.02} />
                <Stat icon={GitCompareArrows} label="Families" value={s.families} help="Variants of one password" tone="var(--warning)" delay={0.06} />
                <Stat icon={CalendarClock} label="Stale" value={s.old} help="Unchanged 6+ months" tone="var(--muted-foreground)" delay={0.1} />
                <Stat
                  icon={report.breach_checked ? AlertOctagon : Lock}
                  label={report.breach_checked ? "Breached" : "2FA on critical"}
                  value={report.breach_checked ? s.breached : mfaCoverage(s.critical_accounts, s.critical_without_mfa)}
                  help={report.breach_checked ? "Seen in public leaks" : "Bank, email & cloud accounts"}
                  tone={report.breach_checked ? "var(--danger)" : "var(--accent)"}
                  delay={0.14}
                />
              </div>
              <TopActions report={report} onFix={open} />
            </div>
          </div>

          <div className="mb-5 mt-8 overflow-x-auto pb-1">
            <Segmented
              value={tab}
              onChange={setTab}
              options={[
                { value: "priorities", label: "Priorities" },
                { value: "families", label: <>Reuse &amp; families {report.families.length > 0 && <Badge tone="warning">{report.families.length}</Badge>}</> },
                { value: "timeline", label: "Timeline" },
                { value: "advisor", label: <><Sparkles className="size-3.5" /> Advisor</> },
                { value: "site", label: "Site check" },
              ]}
            />
          </div>

          {tab === "priorities" && (
            <div className="space-y-7">
              {groups.map((g) => {
                const collapsed = g.priority === "low" && !showLow;
                return (
                  <section key={g.priority}>
                    <button
                      className="mb-3 flex w-full items-center gap-2 text-left"
                      onClick={() => g.priority === "low" && setShowLow((v) => !v)}
                      aria-expanded={!collapsed}
                    >
                      <h2 className="text-lg font-semibold tracking-tight">{PRIORITY_TITLE[g.priority]}</h2>
                      <Badge tone={g.priority === "critical" || g.priority === "high" ? "danger" : g.priority === "medium" ? "warning" : "success"}>{g.entries.length}</Badge>
                      {g.priority === "low" && <ChevronDown className={cn("ml-auto size-5 text-muted-foreground transition", !collapsed && "rotate-180")} />}
                    </button>
                    {!collapsed && (
                      <ul className="glass divide-y overflow-hidden rounded-3xl">
                        {g.entries.map((e) => (
                          <li key={e.ref.id}>
                            <EntryRiskCard entry={e} onFix={open} />
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                );
              })}
            </div>
          )}

          {tab === "families" && (
            report.families.length === 0 ? (
              <EmptyState icon={<CheckCircle2 />} title="No password families" description="None of your passwords are identical or variants of each other." />
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {report.families.map((f) => (
                  <div key={f.id} className="glass rounded-3xl p-5">
                    <div className="mb-3 flex items-center gap-2">
                      <Badge tone={f.kind === "identical" ? "danger" : "warning"}>{f.kind === "identical" ? "identical" : "variants"}</Badge>
                      <span className="text-sm font-medium">{f.summary}</span>
                    </div>
                    <ul className="space-y-2">
                      {f.members.map((m) => (
                        <li key={m.id} className="flex items-center gap-3">
                          <ServiceAvatar service={m.service} className="size-9" />
                          <div className="min-w-0 flex-1 leading-tight">
                            <div className="truncate text-sm font-medium">{m.service}</div>
                            <div className="truncate text-xs text-muted-foreground">{m.username || "—"} · {m.vault}</div>
                          </div>
                          <Button size="sm" variant="ghost" onClick={() => open(m)}>Open</Button>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-3 text-xs text-muted-foreground">Attackers who learn one of these will try the others. Give each account its own password.</p>
                  </div>
                ))}
              </div>
            )
          )}

          {tab === "timeline" && <SecurityTimeline />}
          {tab === "advisor" && <Advisor onOpen={open} />}
          {tab === "site" && <SiteCheckPanel examples={["paypa1.com/login", "github.com", "http://192.168.1.10/admin"]} />}
        </>
      ) : null}
    </div>
  );
}
