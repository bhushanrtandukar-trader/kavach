"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Lock, MoreHorizontal, ShieldCheck, ShieldOff, Trash2, UserCog, UserMinus, UserPlus, UserRoundCheck, Users, Vault as VaultIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { InviteCard, InviteDialog } from "@/components/admin/invite-dialog";
import { PageHeader } from "@/components/page-header";
import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/controls";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/menu";
import { Avatar, Badge, EmptyState, RoleBadge, Skeleton } from "@/components/ui/misc";
import { api, ApiError, type Invite, type OrgRole, type OverviewVault, type Policy, type UserRow } from "@/lib/api";
import { canAdmin, useStatus } from "@/lib/hooks";
import { gradientFor, initials, plural, relativeTime } from "@/lib/utils";

type Tab = "people" | "vaults" | "policy";
type Pending =
  | { kind: "disable"; user: UserRow }
  | { kind: "reset"; user: UserRow }
  | { kind: "delete-vault"; vault: OverviewVault }
  | null;

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");
const STATUS_TONE = { active: "success", invited: "warning", disabled: "neutral" } as const;

// ───────────────────────── people ─────────────────────────
function People({ meId, myRole, orgName }: { meId: string; myRole: OrgRole; orgName: string }) {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: api.users });
  const [inviting, setInviting] = useState(false);
  const [result, setResult] = useState<Invite | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const [filter, setFilter] = useState("");

  const assignable: OrgRole[] = myRole === "owner" ? ["owner", "admin", "member", "auditor"] : ["member", "auditor"];
  const canModify = (u: UserRow) => u.id !== meId && (myRole === "owner" || (myRole === "admin" && (u.role === "member" || u.role === "auditor")));
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  const ok = (msg: string) => async () => (toast.success(msg), setPending(null), refresh());

  const setRole = useMutation({ mutationFn: (v: { id: string; role: OrgRole }) => api.setRole(v.id, v.role), onSuccess: ok("Role updated"), onError: (e) => (toast.error(errText(e)), refresh()) });
  const disable = useMutation({ mutationFn: (id: string) => api.disableUser(id), onSuccess: ok("Account disabled and signed out"), onError: (e) => (toast.error(errText(e)), setPending(null)) });
  const enable = useMutation({ mutationFn: (id: string) => api.enableUser(id), onSuccess: ok("Account re-enabled"), onError: (e) => toast.error(errText(e)) });
  const resetMfa = useMutation({ mutationFn: (id: string) => api.resetMfa(id), onSuccess: ok("Two-factor reset"), onError: (e) => toast.error(errText(e)) });
  const reissue = useMutation({ mutationFn: (id: string) => api.reissueInvite(id), onSuccess: (r) => (setResult(r), refresh()), onError: (e) => toast.error(errText(e)) });
  const reset = useMutation({
    mutationFn: (id: string) => api.resetAccess(id),
    onSuccess: async (r) => (setPending(null), setResult(r), await refresh()),
    onError: (e) => (toast.error(errText(e)), setPending(null)),
  });

  const rows = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (users.data ?? []).filter((u) => !q || `${u.username} ${u.display_name} ${u.email}`.toLowerCase().includes(q));
  }, [users.data, filter]);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input className="max-w-xs" placeholder="Filter people…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter people" />
        <Button className="ml-auto" onClick={() => setInviting(true)}>
          <UserPlus /> Invite someone
        </Button>
      </div>

      <div className="glass overflow-hidden rounded-3xl">
        <div className="hidden grid-cols-[minmax(0,2fr)_150px_120px_90px_120px_44px] items-center gap-3 border-b px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground md:grid">
          <span>Person</span>
          <span>Role</span>
          <span>Status</span>
          <span>2FA</span>
          <span>Last sign-in</span>
          <span />
        </div>
        {users.isLoading ? (
          <div className="space-y-px p-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div>
        ) : rows.length === 0 ? (
          <EmptyState icon={<Users />} title="No one matches" description="Try a different name." />
        ) : (
          <ul className="divide-y">
            {rows.map((u) => (
              <li key={u.id} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-2 px-5 py-3.5 hover:bg-muted/50 md:grid-cols-[minmax(0,2fr)_150px_120px_90px_120px_44px]">
                <div className="flex min-w-0 items-center gap-3">
                  <Avatar name={u.display_name} gradient={gradientFor(u.username)} className="size-10">
                    {initials(u.display_name)}
                  </Avatar>
                  <div className="min-w-0 leading-tight">
                    <div className="truncate font-medium">
                      {u.display_name} {u.id === meId && <span className="text-xs font-normal text-muted-foreground">(you)</span>}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">@{u.username}{u.email ? ` · ${u.email}` : ""}</div>
                  </div>
                </div>
                <div className="col-start-1 md:col-start-auto">
                  {canModify(u) && u.status !== "invited" ? (
                    <Select value={u.role} onValueChange={(v) => setRole.mutate({ id: u.id, role: v as OrgRole })}>
                      <SelectTrigger className="h-9 w-32 text-[13px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {assignable.map((r) => (
                          <SelectItem key={r} value={r}>{r[0]!.toUpperCase() + r.slice(1)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <RoleBadge role={u.role} />
                  )}
                </div>
                <div><Badge tone={STATUS_TONE[u.status as keyof typeof STATUS_TONE] ?? "neutral"}>{u.status === "invited" ? "pending invite" : u.status}</Badge></div>
                <div className="hidden md:block">
                  {u.totp_enabled ? <span className="inline-flex items-center gap-1 text-xs text-success"><ShieldCheck className="size-4" /> On</span> : <span className="text-xs text-muted-foreground">—</span>}
                </div>
                <div className="hidden text-xs text-muted-foreground md:block">{u.last_login ? relativeTime(u.last_login) : "never"}</div>
                <div className="justify-self-end">
                  {canModify(u) ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${u.username}`}>
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {u.status === "invited" && (
                          <DropdownMenuItem onSelect={() => reissue.mutate(u.id)}><KeyRound /> New invite code</DropdownMenuItem>
                        )}
                        {u.status === "disabled" && (
                          <DropdownMenuItem onSelect={() => enable.mutate(u.id)}><UserRoundCheck /> Re-enable</DropdownMenuItem>
                        )}
                        {u.status === "active" && u.totp_enabled && (
                          <DropdownMenuItem onSelect={() => resetMfa.mutate(u.id)}><ShieldOff /> Reset two-factor</DropdownMenuItem>
                        )}
                        {u.status !== "disabled" && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem danger onSelect={() => setPending({ kind: "reset", user: u })}><UserCog /> Reset access…</DropdownMenuItem>
                            <DropdownMenuItem danger onSelect={() => setPending({ kind: "disable", user: u })}><UserMinus /> Disable account…</DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : (
                    <span className="block size-8" />
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <InviteDialog open={inviting} onOpenChange={setInviting} assignable={assignable} orgName={orgName} />
      <Dialog open={result !== null} onOpenChange={(o) => !o && setResult(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New invite code</DialogTitle>
            <DialogDescription>The previous code no longer works.</DialogDescription>
          </DialogHeader>
          {result && <InviteCard invite={result} orgName={orgName} />}
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={pending?.kind === "disable"}
        onOpenChange={(o) => !o && setPending(null)}
        title={`Disable @${pending?.kind === "disable" ? pending.user.username : ""}?`}
        description="They are signed out immediately and removed from every shared vault, and those vaults' keys are replaced. Their personal vault stays, locked, until they're re-enabled."
        confirmLabel="Disable"
        loading={disable.isPending}
        onConfirm={() => pending?.kind === "disable" && disable.mutate(pending.user.id)}
      />
      <ConfirmDialog
        open={pending?.kind === "reset"}
        onOpenChange={(o) => !o && setPending(null)}
        title={`Reset access for @${pending?.kind === "reset" ? pending.user.username : ""}?`}
        description="Use this only if they've forgotten their master password. Their personal vault is permanently deleted (nobody can recover it), they lose access to shared vaults until re-added, and they get a new invite code."
        confirmLabel="Reset access"
        loading={reset.isPending}
        onConfirm={() => pending?.kind === "reset" && reset.mutate(pending.user.id)}
      />
    </>
  );
}

// ───────────────────────── vaults ─────────────────────────
function VaultsOverview() {
  const qc = useQueryClient();
  const overview = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  const [pending, setPending] = useState<OverviewVault | null>(null);
  const del = useMutation({
    mutationFn: (id: string) => api.deleteVault(id),
    onSuccess: async () => {
      toast.success("Vault deleted");
      setPending(null);
      await Promise.all([qc.invalidateQueries({ queryKey: ["overview"] }), qc.invalidateQueries({ queryKey: ["vaults"] })]);
    },
    onError: (e) => (toast.error(errText(e)), setPending(null)),
  });
  return (
    <>
      <p className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
        <Lock className="size-4" /> Administrators can see that a vault exists and who is in it, never what is inside.
      </p>
      <div className="glass overflow-hidden rounded-3xl">
        {overview.isLoading ? (
          <div className="space-y-px p-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>
        ) : (overview.data ?? []).length === 0 ? (
          <EmptyState icon={<VaultIcon />} title="No vaults yet" />
        ) : (
          <ul className="divide-y">
            {(overview.data ?? []).map((v) => (
              <li key={v.id} className="flex flex-wrap items-center gap-4 px-5 py-3.5 hover:bg-muted/50">
                <span style={{ background: v.kind === "personal" ? "linear-gradient(135deg,#6b46ff,#a855f7)" : gradientFor(v.name) }} className="flex size-10 items-center justify-center rounded-xl text-white">
                  {v.kind === "personal" ? <Lock className="size-4" /> : <span className="text-sm font-bold">{initials(v.name).slice(0, 1)}</span>}
                </span>
                <div className="min-w-0 flex-1 basis-48 leading-tight">
                  <div className="truncate font-medium">{v.kind === "personal" ? `Personal — @${v.created_by}` : v.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {v.kind === "shared" ? `created by @${v.created_by} · ` : ""}{plural(v.member_count, "member")} · {plural(v.entry_count, "entry", "entries")}
                  </div>
                </div>
                {v.needs_rotation ? <Badge tone="warning">key rotation pending</Badge> : null}
                <Badge>{v.kind}</Badge>
                {v.kind === "shared" ? (
                  <Button variant="ghost" size="icon-sm" aria-label={`Delete ${v.name}`} className="text-muted-foreground hover:text-danger" onClick={() => setPending(v)}>
                    <Trash2 />
                  </Button>
                ) : <span className="size-8" />}
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        title={`Delete “${pending?.name}”?`}
        description={`This permanently deletes the vault and its ${pending?.entry_count ?? 0} entries for all ${pending?.member_count ?? 0} members. It cannot be undone.`}
        confirmLabel="Delete vault"
        loading={del.isPending}
        onConfirm={() => pending && del.mutate(pending.id)}
      />
    </>
  );
}

// ───────────────────────── policy ─────────────────────────
const POLICY_FIELDS: { key: keyof Omit<Policy, "breach_check">; label: string; hint: string; min: number; max: number; unit: string }[] = [
  { key: "min_password_length", label: "Minimum password length", hint: "Applies to new and changed master passwords.", min: 8, max: 128, unit: "characters" },
  { key: "idle_timeout_secs", label: "Sign out after inactivity", hint: "Also enforced by the server.", min: 60, max: 86400, unit: "seconds" },
  { key: "max_attempts", label: "Failed sign-ins before lockout", hint: "Counted per account.", min: 3, max: 20, unit: "attempts" },
  { key: "lockout_secs", label: "Lockout length", hint: "How long the account waits.", min: 30, max: 86400, unit: "seconds" },
  { key: "invite_ttl_hours", label: "Invite validity", hint: "How long an invite code works.", min: 1, max: 720, unit: "hours" },
];

function PolicyForm() {
  const qc = useQueryClient();
  const policy = useQuery({ queryKey: ["policy"], queryFn: api.policy });
  const [draft, setDraft] = useState<Partial<Record<keyof Policy, number>>>({});
  const value = (k: keyof Policy) => draft[k] ?? policy.data?.[k] ?? 0;
  const dirty = Object.keys(draft).length > 0;

  const save = useMutation({
    mutationFn: () => api.setPolicy(draft),
    onSuccess: async (p) => {
      toast.success("Policy saved");
      setDraft({});
      qc.setQueryData(["policy"], p);
      await qc.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (e) => toast.error(errText(e)),
  });

  if (policy.isLoading || !policy.data) return <Skeleton className="h-96" />;
  return (
    <div className="glass rounded-3xl p-6">
      <div className="grid gap-5 sm:grid-cols-2">
        {POLICY_FIELDS.map((f) => (
          <Field key={f.key} label={f.label} hint={`${f.hint} (${f.min}–${f.max} ${f.unit})`}>
            <Input type="number" min={f.min} max={f.max} value={value(f.key)} onChange={(e) => setDraft((d) => ({ ...d, [f.key]: Number(e.target.value) }))} />
          </Field>
        ))}
        <div className="flex items-start justify-between gap-4 rounded-2xl border p-4 sm:col-span-2">
          <div>
            <div className="font-medium">Allow breach checks</div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Lets people check their passwords against known breaches. Only the first 5 characters of each password&apos;s SHA-1 hash are sent to api.pwnedpasswords.com, from this server. Off by default.
            </p>
          </div>
          <Switch checked={value("breach_check") === 1} onCheckedChange={(c) => setDraft((d) => ({ ...d, breach_check: c ? 1 : 0 }))} />
        </div>
      </div>
      <div className="mt-6 flex justify-end gap-2">
        {dirty && <Button variant="ghost" onClick={() => setDraft({})}>Discard</Button>}
        <Button disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>Save policy</Button>
      </div>
    </div>
  );
}

// ───────────────────────── page ─────────────────────────
export default function AdminPage() {
  const status = useStatus();
  const me = status.data?.me;
  const [tab, setTab] = useState<Tab>("people");

  if (!me) return null;
  if (!canAdmin(me.role)) {
    return <EmptyState icon={<ShieldOff />} title="Administrators only" description="You don't have access to this page." />;
  }
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="People & policy" description={`Manage who can use ${status.data?.org_name ?? "your organisation"} and how strict it is.`} />
      <Segmented
        className="mb-5"
        value={tab}
        onChange={setTab}
        options={[
          { value: "people", label: <><Users className="size-4" /> People</> },
          { value: "vaults", label: <><VaultIcon className="size-4" /> Vaults</> },
          { value: "policy", label: <><ShieldCheck className="size-4" /> Security policy</> },
        ]}
      />
      {tab === "people" && <People meId={me.id} myRole={me.role as OrgRole} orgName={status.data?.org_name ?? ""} />}
      {tab === "vaults" && <VaultsOverview />}
      {tab === "policy" && <PolicyForm />}
    </div>
  );
}
