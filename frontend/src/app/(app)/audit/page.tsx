"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Clock, Download, KeyRound, Lock, MapPin, Radar, ScrollText, ShieldAlert, ShieldCheck, ShieldX, UserCog } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge, EmptyState, Skeleton } from "@/components/ui/misc";
import { api, ApiError, type AuditRow, type Finding } from "@/lib/api";
import { canAudit, useDebounced, useStatus } from "@/lib/hooks";
import { cn, formatDateTime, relativeTime } from "@/lib/utils";

const LABEL: Record<string, string> = {
  "auth.login": "Signed in", "auth.logout": "Signed out", "auth.login_failed": "Failed sign-in", "auth.locked": "Account locked",
  "org.bootstrap": "Organisation created", "user.invite": "Invited a person", "user.activate": "Activated account", "user.role": "Changed a role",
  "user.disable": "Disabled an account", "user.enable": "Re-enabled an account", "user.reset_access": "Reset someone's access", "user.reinvite": "Issued a new invite code",
  "user.change_password": "Changed password", "user.mfa_enable": "Turned on two-factor", "user.mfa_disable": "Turned off two-factor", "user.mfa_reset": "Reset someone's two-factor",
  "vault.create": "Created a vault", "vault.update": "Edited a vault", "vault.delete": "Deleted a vault", "vault.member_add": "Added someone to a vault",
  "vault.member_role": "Changed a vault role", "vault.member_remove": "Removed someone from a vault", "vault.rotate_key": "Replaced a vault key",
  "vault.reveal_all": "Revealed all passwords", "vault.health_scan": "Ran a health check", "entry.create": "Added an entry", "entry.update": "Edited an entry",
  "entry.delete": "Deleted entries", "entry.reveal": "Viewed a password", "entry.copy": "Copied a password", "policy.update": "Changed the security policy",
};

const CATEGORIES = [
  { value: "", label: "Everything" },
  { value: "auth.", label: "Sign-ins" },
  { value: "user.", label: "People" },
  { value: "vault.", label: "Vaults" },
  { value: "entry.", label: "Secrets" },
  { value: "policy.", label: "Policy" },
];

function tone(action: string): { color: string; icon: React.ComponentType<{ className?: string }> } {
  if (action === "auth.login_failed" || action === "auth.locked") return { color: "var(--danger)", icon: ShieldAlert };
  if (action === "entry.reveal" || action === "entry.copy" || action === "vault.reveal_all") return { color: "var(--warning)", icon: KeyRound };
  if (action.startsWith("auth.")) return { color: "var(--accent)", icon: Lock };
  if (action.startsWith("user.") || action.startsWith("policy.") || action === "org.bootstrap") return { color: "var(--primary)", icon: UserCog };
  return { color: "var(--muted-foreground)", icon: ScrollText };
}

function shortTarget(t: string) {
  if (t.includes("/")) return t.split("/").map((p) => p.slice(0, 8)).join("/");
  return /^[0-9a-f]{32}$/.test(t) ? t.slice(0, 8) + "…" : t;
}

const KIND_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  bulk_access: Download, new_location: MapPin, odd_hour: Clock, password_spraying: Radar, guessed_password: KeyRound, risky_admin_act: UserCog, lockout: Lock,
};
const SEV: Record<string, { color: string; tone: "danger" | "warning" | "neutral" }> = {
  high: { color: "var(--danger)", tone: "danger" },
  medium: { color: "var(--warning)", tone: "warning" },
  low: { color: "var(--muted-foreground)", tone: "neutral" },
};

function InsightCard({ f, i }: { f: Finding; i: number }) {
  const Icon = KIND_ICON[f.kind] ?? ShieldAlert;
  const sev = SEV[f.severity] ?? SEV.low!;
  return (
    <motion.li initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.05 }} className="relative flex gap-4 px-5 py-4">
      <span className="absolute inset-y-3 left-0 w-1 rounded-r-full" style={{ background: sev.color }} />
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl" style={{ background: `color-mix(in oklab, ${sev.color} 15%, transparent)`, color: sev.color }}>
        <Icon className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={sev.tone}>{f.severity}</Badge>
          <span className="font-medium">{f.title}</span>
          <span className="text-xs text-muted-foreground" title={formatDateTime(f.ts)}>{relativeTime(f.ts)}</span>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{f.detail}</p>
        <p className="mt-1 text-sm">{f.advice}</p>
      </div>
    </motion.li>
  );
}

export default function AuditPage() {
  const me = useStatus().data?.me;
  const [cat, setCat] = useState("");
  const [actor, setActor] = useState("");
  const dActor = useDebounced(actor, 250);

  const insights = useQuery({ queryKey: ["insights"], queryFn: () => api.insights(7), enabled: !!me && canAudit(me.role) });
  const log = useQuery({ queryKey: ["audit", cat, dActor], queryFn: () => api.audit(cat, dActor, 300), enabled: !!me && canAudit(me.role), placeholderData: (p) => p });
  const verify = useMutation({ mutationFn: api.verifyAudit });

  if (!me) return null;
  if (!canAudit(me.role)) return <EmptyState icon={<ShieldX />} title="Not available" description="Only owners, admins and auditors can read the audit log." />;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Audit & insights" description="Everything sensitive that happens is recorded here, in a chain that shows if anyone tampers with it." />

      {/* insights */}
      <section className="mb-8">
        <div className="mb-3 flex items-center gap-2">
          <Radar className="size-5 text-primary" />
          <h2 className="text-lg font-semibold tracking-tight">Security insights</h2>
          <span className="text-sm text-muted-foreground">last 7 days, compared with each person&apos;s own normal</span>
        </div>
        {insights.isLoading ? (
          <Skeleton className="h-28" />
        ) : insights.isError ? (
          <div className="glass rounded-3xl p-5 text-sm text-danger">{insights.error instanceof ApiError ? insights.error.message : "Could not load insights."}</div>
        ) : (insights.data?.findings.length ?? 0) === 0 ? (
          <div className="glass flex items-center gap-4 rounded-3xl p-5">
            <span className="flex size-12 items-center justify-center rounded-2xl bg-success/15 text-success"><ShieldCheck className="size-6" /></span>
            <div>
              <div className="font-medium">Nothing unusual.</div>
              <div className="text-sm text-muted-foreground">{insights.data?.events_analysed.toLocaleString()} events analysed against each person&apos;s baseline.</div>
            </div>
          </div>
        ) : (
          <ul className="glass divide-y overflow-hidden rounded-3xl">
            {insights.data!.findings.slice(0, 25).map((f, i) => <InsightCard key={i} f={f} i={i} />)}
          </ul>
        )}
      </section>

      {/* log */}
      <section>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <ScrollText className="size-5 text-primary" />
            <h2 className="text-lg font-semibold tracking-tight">Activity log</h2>
          </div>
          <Button variant="outline" size="sm" className="ml-auto" loading={verify.isPending} onClick={() => verify.mutate()}>
            <ShieldCheck /> Verify integrity
          </Button>
        </div>

        <AnimatePresence>
          {verify.data && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
              <div className={cn("mb-3 flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm", verify.data.ok ? "border-success/25 bg-success/10 text-success" : "border-danger/30 bg-danger/10 text-danger")}>
                {verify.data.ok ? <ShieldCheck className="size-5" /> : <ShieldX className="size-5" />}
                {verify.data.ok ? `All ${verify.data.checked.toLocaleString()} events form an unbroken chain — nothing has been altered or removed.` : `The log has been altered: the chain breaks at event #${verify.data.first_bad_id}.`}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="mb-3 flex flex-wrap items-center gap-3">
          <Segmented value={cat} onChange={setCat} options={CATEGORIES} />
          <Input className="max-w-52" placeholder="Filter by username" value={actor} onChange={(e) => setActor(e.target.value)} aria-label="Filter by username" />
        </div>

        <div className="glass overflow-hidden rounded-3xl">
          {log.isLoading ? (
            <div className="space-y-px p-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
          ) : (log.data ?? []).length === 0 ? (
            <EmptyState icon={<ScrollText />} title="No events" description="Nothing matches those filters." />
          ) : (
            <ul className="divide-y">
              {(log.data as AuditRow[]).map((r) => {
                const t = tone(r.action);
                const Icon = t.icon;
                return (
                  <li key={r.id} className="flex items-start gap-4 px-5 py-3 hover:bg-muted/40">
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg" style={{ background: `color-mix(in oklab, ${t.color} 15%, transparent)`, color: t.color }}>
                      <Icon className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className="text-sm font-medium">{LABEL[r.action] ?? r.action}</span>
                        <span className="text-sm text-muted-foreground">by <b className="font-medium text-foreground/80">{r.actor_name}</b></span>
                      </div>
                      {(r.target || r.detail) && (
                        <div className="truncate text-xs text-muted-foreground">
                          {shortTarget(r.target)}{r.target && r.detail ? " · " : ""}{r.detail}
                        </div>
                      )}
                    </div>
                    <div className="shrink-0 text-right text-xs text-muted-foreground" title={formatDateTime(r.ts)}>
                      <div>{relativeTime(r.ts)}</div>
                      {r.ip && <div className="font-mono text-[11px] opacity-70">{r.ip}</div>}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
