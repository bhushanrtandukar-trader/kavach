"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EyeOff, Eye, HeartPulse, KeyRound, Lock, Plus, Search, SearchX, Trash2, Users, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EntryRow } from "@/components/entries/entry-row";
import { EntrySheet, type SheetState } from "@/components/entries/entry-sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, EmptyState, Kbd, RoleBadge, Skeleton } from "@/components/ui/misc";
import { AccessDialog, NewVaultDialog } from "@/components/vault-dialogs";
import { useVault } from "@/components/vault-context";
import { api, ApiError } from "@/lib/api";
import { on, takePendingOpen } from "@/lib/events";
import { canCreateVault, useDebounced, useStatus } from "@/lib/hooks";
import { gradientFor, initials, plural } from "@/lib/utils";

const REVEAL_MS = 15_000;

export default function VaultsPage() {
  const qc = useQueryClient();
  const me = useStatus().data?.me;
  const { vault, vaultId, loading: vaultsLoading, select } = useVault();
  const canWrite = vault?.role === "manager" || vault?.role === "editor";
  const shared = vault?.kind === "shared";

  const [q, setQ] = useState("");
  const dq = useDebounced(q, 180);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sheet, setSheet] = useState<SheetState>({ open: false, entryId: null });
  const [toDelete, setToDelete] = useState<string[] | null>(null);
  const [newVault, setNewVault] = useState(false);
  const [access, setAccess] = useState(false);
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [allShown, setAllShown] = useState(false);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const searchRef = useRef<HTMLInputElement>(null);

  const entries = useQuery({
    queryKey: ["entries", vaultId, dq],
    queryFn: () => api.entries(vaultId!, dq),
    enabled: !!vaultId,
    placeholderData: (prev) => prev,
  });
  const members = useQuery({ queryKey: ["members", vaultId], queryFn: () => api.members(vaultId!), enabled: !!vaultId && shared });

  // ── hide secrets whenever the context changes ──
  const hideAll = useCallback(() => {
    Object.values(timers.current).forEach(clearTimeout);
    timers.current = {};
    setRevealed({});
    setAllShown(false);
  }, []);
  useEffect(() => {
    hideAll();
    setSelected(new Set());
    setQ("");
  }, [vaultId, hideAll]);
  useEffect(() => hideAll, [hideAll]);

  async function toggleReveal(id: string) {
    if (revealed[id] !== undefined) {
      clearTimeout(timers.current[id]);
      setRevealed((r) => {
        const { [id]: _drop, ...rest } = r;
        return rest;
      });
      return;
    }
    try {
      const { password } = await api.entryPassword(vaultId!, id, "view");
      setRevealed((r) => ({ ...r, [id]: password }));
      timers.current[id] = setTimeout(() => {
        setRevealed((r) => {
          const { [id]: _drop, ...rest } = r;
          return rest;
        });
      }, REVEAL_MS);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not reveal that password");
    }
  }

  async function toggleRevealAll() {
    if (allShown) return hideAll();
    try {
      const { passwords } = await api.revealAll(vaultId!);
      setRevealed(passwords);
      setAllShown(true);
      timers.current["*"] = setTimeout(hideAll, REVEAL_MS + 5_000);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not reveal passwords");
    }
  }

  const del = useMutation({
    mutationFn: (ids: string[]) => api.deleteEntries(vaultId!, ids),
    onSuccess: async (r) => {
      toast.success(`Deleted ${plural(r.deleted, "entry", "entries")}`);
      setToDelete(null);
      setSelected(new Set());
      setSheet({ open: false, entryId: null });
      await Promise.all([qc.invalidateQueries({ queryKey: ["entries", vaultId] }), qc.invalidateQueries({ queryKey: ["vaults"] })]);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not delete"),
  });

  // ── things other parts of the app can ask this page to do ──
  const openNew = useCallback(() => {
    if (!canWrite) return toast.info("This vault is read-only for you.");
    setSheet({ open: true, entryId: null });
  }, [canWrite]);

  useEffect(() => on("gk:new-entry", openNew), [openNew]);
  useEffect(() => on("gk:new-vault", () => canCreateVault(me?.role) && setNewVault(true)), [me?.role]);
  useEffect(
    () =>
      on("gk:open-entry", (d) => {
        select(d.vaultId);
        setSheet({ open: true, entryId: d.entryId });
      }),
    [select],
  );
  useEffect(() => {
    const p = takePendingOpen();
    if (p) {
      select(p.vaultId);
      setSheet({ open: true, entryId: p.entryId });
    }
  }, [select]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, [contenteditable], [role=dialog]") || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/") (e.preventDefault(), searchRef.current?.focus());
      if (e.key === "n") (e.preventDefault(), openNew());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openNew]);

  const list = useMemo(() => entries.data ?? [], [entries.data]);
  const allSelected = list.length > 0 && list.every((e) => selected.has(e.id));
  const toggleSelect = (id: string, on: boolean) =>
    setSelected((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });

  if (vaultsLoading || !vault) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-16 w-72" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  const vaultTitle = vault.kind === "personal" ? "Personal vault" : vault.name;
  const stack = (members.data ?? []).slice(0, 4);

  return (
    <div className="mx-auto max-w-6xl">
      {/* header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <span
            style={{ background: vault.kind === "personal" ? "linear-gradient(135deg,#6b46ff,#a855f7)" : gradientFor(vault.name) }}
            className="flex size-14 shrink-0 items-center justify-center rounded-2xl text-white shadow-lg ring-1 ring-white/10"
          >
            {vault.kind === "personal" ? <Lock className="size-6" /> : <span className="text-xl font-bold">{initials(vault.name).slice(0, 1)}</span>}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="truncate text-2xl font-semibold tracking-tight sm:text-3xl">{vaultTitle}</h1>
              {shared ? <RoleBadge role={vault.role} /> : <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Only you</span>}
            </div>
            <p className="mt-0.5 truncate text-sm text-muted-foreground">
              {vault.description || (vault.kind === "personal" ? "Your private passwords. Nobody else can open this." : "A shared vault.")} · {plural(vault.entry_count, "entry", "entries")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {shared && (
            <button onClick={() => setAccess(true)} className="group flex items-center gap-2 rounded-xl px-2 py-1.5 transition hover:bg-muted" aria-label="Manage access">
              <span className="flex -space-x-2">
                {stack.map((m) => (
                  <Avatar key={m.user_id} name={m.display_name} gradient={gradientFor(m.username)} className="size-8 rounded-full text-[10px] ring-2 ring-background">
                    {initials(m.display_name)}
                  </Avatar>
                ))}
                {vault.member_count > stack.length && (
                  <span className="flex size-8 items-center justify-center rounded-full bg-muted text-[10px] font-semibold ring-2 ring-background">+{vault.member_count - stack.length}</span>
                )}
              </span>
              <span className="hidden items-center gap-1 text-sm text-muted-foreground group-hover:text-foreground sm:flex">
                <Users className="size-4" /> Access
              </span>
            </button>
          )}
          <Link href="/health">
            <Button variant="secondary">
              <HeartPulse /> Health
            </Button>
          </Link>
          {canWrite && (
            <Button onClick={openNew}>
              <Plus /> Add entry
            </Button>
          )}
        </div>
      </div>

      {/* toolbar */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 max-w-md flex-1">
          <Input ref={searchRef} icon={<Search />} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search this vault — typos are fine" aria-label="Search entries" />
          {q ? (
            <button aria-label="Clear search" onClick={() => setQ("")} className="absolute right-2.5 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-muted">
              <X className="size-4" />
            </button>
          ) : (
            <Kbd className="absolute right-3 top-1/2 -translate-y-1/2">/</Kbd>
          )}
        </div>
        <Button variant="outline" onClick={() => void toggleRevealAll()} disabled={list.length === 0}>
          {allShown ? <EyeOff /> : <Eye />} {allShown ? "Hide all" : "Reveal all"}
        </Button>
        <AnimatePresence>
          {selected.size > 0 && canWrite && (
            <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }} className="ml-auto flex items-center gap-2 rounded-xl bg-primary/10 py-1 pl-3 pr-1 text-sm">
              <span className="font-medium">{selected.size} selected</span>
              <Button size="sm" variant="destructive" onClick={() => setToDelete([...selected])}>
                <Trash2 /> Delete
              </Button>
              <Button size="icon-sm" variant="ghost" aria-label="Clear selection" onClick={() => setSelected(new Set())}>
                <X />
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* list */}
      <div className="glass overflow-hidden rounded-3xl">
        {list.length > 0 && (
          <div className="hidden grid-cols-[auto_minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.1fr)_auto_auto] items-center gap-x-3 border-b px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground sm:grid">
            <span className="w-[18px]" />
            <span>Name</span>
            <span>Username</span>
            <span>Password</span>
            <span className="w-16">Updated</span>
            <span className="w-8" />
          </div>
        )}
        {entries.isLoading ? (
          <div className="space-y-px p-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : entries.isError ? (
          <EmptyState icon={<SearchX />} title="Couldn't load this vault" description={entries.error instanceof ApiError ? entries.error.message : "Try again in a moment."} action={<Button onClick={() => entries.refetch()}>Retry</Button>} />
        ) : list.length === 0 ? (
          dq ? (
            <EmptyState icon={<SearchX />} title="No matches" description={`Nothing in this vault looks like “${dq}”.`} action={<Button variant="secondary" onClick={() => setQ("")}>Clear search</Button>} />
          ) : (
            <EmptyState
              icon={<KeyRound />}
              title="This vault is empty"
              description={canWrite ? "Add your first login. It's encrypted before it touches the disk." : "Nothing here yet."}
              action={canWrite ? <Button onClick={openNew}><Plus /> Add entry</Button> : undefined}
            />
          )
        ) : (
          <ul className="divide-y">
            <AnimatePresence initial={false}>
              {list.map((e) => (
                <EntryRow
                  key={e.id}
                  entry={e}
                  vaultId={vaultId!}
                  selected={selected.has(e.id)}
                  onSelect={(on) => toggleSelect(e.id, on)}
                  canWrite={!!canWrite}
                  revealed={revealed[e.id]}
                  onToggleReveal={() => void toggleReveal(e.id)}
                  onEdit={() => setSheet({ open: true, entryId: e.id })}
                  onDelete={() => setToDelete([e.id])}
                />
              ))}
            </AnimatePresence>
          </ul>
        )}
        {list.length > 1 && canWrite && (
          <div className="flex items-center gap-2 border-t px-4 py-2 text-xs text-muted-foreground">
            <button className="rounded-md px-2 py-1 hover:bg-muted" onClick={() => setSelected(allSelected ? new Set() : new Set(list.map((e) => e.id)))}>
              {allSelected ? "Clear selection" : "Select all"}
            </button>
            <span className="ml-auto hidden items-center gap-2 sm:flex">
              <Kbd>n</Kbd> new entry <Kbd>/</Kbd> search
            </span>
          </div>
        )}
      </div>

      <EntrySheet
        vaultId={vaultId!}
        vaultName={vaultTitle}
        state={sheet}
        canWrite={!!canWrite}
        onOpenChange={(open) => setSheet((s) => ({ ...s, open }))}
        onDelete={(id) => setToDelete([id])}
      />
      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`Delete ${toDelete ? plural(toDelete.length, "entry", "entries") : ""}?`}
        description="This can't be undone. Anyone with access to this vault will lose them too."
        confirmLabel="Delete"
        loading={del.isPending}
        onConfirm={() => toDelete && del.mutate(toDelete)}
      />
      <NewVaultDialog open={newVault} onOpenChange={setNewVault} onCreated={select} />
      {shared && <AccessDialog vault={vault} open={access} onOpenChange={setAccess} onGone={() => qc.invalidateQueries({ queryKey: ["vaults"] })} />}
    </div>
  );
}
