"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FishSymbol, Globe, KeyRound, ShieldCheck, StickyNote, Trash2, User } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PasswordGenerator } from "@/components/entries/password-generator";
import { StrengthMeter } from "@/components/strength-meter";
import { EntryRiskCard } from "@/components/security/parts";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/controls";
import { SheetContent } from "@/components/ui/dialog";
import { Field, Input, PasswordInput, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { api, ApiError, type EntryInput } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";

const EMPTY: EntryInput = { service: "", username: "", password: "", url: "", notes: "", mfa: false };

export interface SheetState {
  open: boolean;
  entryId: string | null; // null = new entry
}

export function EntrySheet({
  vaultId,
  vaultName,
  state,
  canWrite,
  onOpenChange,
  onDelete,
}: {
  vaultId: string;
  vaultName: string;
  state: SheetState;
  canWrite: boolean;
  onOpenChange: (open: boolean) => void;
  onDelete: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<EntryInput>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const editing = state.entryId !== null;

  // The decrypted entry is fetched only while the sheet is open and is never cached (gcTime 0),
  // so a password does not linger in memory after you close it.
  const entry = useQuery({
    queryKey: ["entry", vaultId, state.entryId],
    queryFn: () => api.entry(vaultId, state.entryId!),
    enabled: state.open && editing,
    gcTime: 0,
    staleTime: 0,
  });

  useEffect(() => {
    if (!state.open) return;
    setError(null);
    if (!editing) setForm(EMPTY);
  }, [state.open, editing, state.entryId]);

  useEffect(() => {
    if (entry.data) {
      const { service, username, password, url, notes, mfa } = entry.data;
      setForm({ service, username, password, url, notes, mfa: !!mfa });
    }
  }, [entry.data]);

  useEffect(() => {
    if (!state.open) {
      setForm(EMPTY); // wipe plaintext from component state on close
      qc.removeQueries({ queryKey: ["entry", vaultId] });
    }
  }, [state.open, qc, vaultId]);

  // How risky is this account? A quiet lookup (cached, unaudited); the full scan lives on the Security page.
  const intel = useQuery({
    queryKey: ["intel-quiet"],
    queryFn: () => api.intel(false, true),
    enabled: state.open && editing,
    staleTime: 60_000,
  });
  const risk = intel.data?.entries.find((e) => e.ref.id === state.entryId);

  const urlWarn = useQuery({
    queryKey: ["url-check", useDebounced(form.url, 300)],
    queryFn: () => api.urlCheck(form.url),
    enabled: state.open && form.url.trim().length > 3,
    staleTime: Infinity,
  });

  const save = useMutation({
    mutationFn: async () => {
      if (editing) await api.updateEntry(vaultId, state.entryId!, form);
      else await api.addEntry(vaultId, form);
    },
    onSuccess: async () => {
      toast.success(editing ? "Entry saved" : "Entry added");
      await Promise.all([qc.invalidateQueries({ queryKey: ["entries", vaultId] }), qc.invalidateQueries({ queryKey: ["vaults"] })]);
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not save."),
  });

  const set = (k: keyof EntryInput) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const readOnly = editing && !canWrite;
  const loading = editing && entry.isLoading;

  return (
    <DialogPrimitive.Root open={state.open} onOpenChange={onOpenChange}>
      <SheetContent aria-describedby={undefined}>
        <div className="border-b px-6 pb-4 pt-6">
          <DialogPrimitive.Title className="pr-10 text-xl font-semibold tracking-tight">
            {readOnly ? "Entry details" : editing ? "Edit entry" : "New entry"}
          </DialogPrimitive.Title>
          <p className="mt-1 text-sm text-muted-foreground">
            {readOnly ? "You have read-only access to this vault." : `Saved to ${vaultName}, encrypted with its key.`}
          </p>
        </div>

        <form
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(e) => {
            e.preventDefault();
            if (!readOnly) save.mutate();
          }}
        >
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-5">
            {error && (
              <div role="alert" className="flex items-start gap-2 rounded-xl border border-danger/25 bg-danger/10 px-3 py-2.5 text-sm text-danger">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {error}
              </div>
            )}
            {loading ? (
              <div className="space-y-5">
                {[0, 1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-11" />
                ))}
              </div>
            ) : (
              <>
                <Field label="Service">
                  <Input autoFocus={!editing} placeholder="e.g. GitHub, AWS console" value={form.service} onChange={set("service")} readOnly={readOnly} required maxLength={200} />
                </Field>
                <Field label="Username or email">
                  <Input icon={<User />} autoComplete="off" value={form.username ?? ""} onChange={set("username")} readOnly={readOnly} maxLength={200} />
                </Field>
                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="text-[13px] font-medium text-foreground/80">Password</span>
                    {!readOnly && <PasswordGenerator onUse={(p) => setForm((f) => ({ ...f, password: p }))} />}
                  </div>
                  <PasswordInput value={form.password} onChange={set("password")} readOnly={readOnly} required maxLength={1000} />
                  {!readOnly && <StrengthMeter className="mt-2.5" password={form.password} inputs={[form.service, form.username ?? ""]} />}
                </div>
                <div>
                  <Field label="Website">
                    <Input icon={<Globe />} placeholder="https://" value={form.url ?? ""} onChange={set("url")} readOnly={readOnly} maxLength={500} />
                  </Field>
                  {urlWarn.data && urlWarn.data.length > 0 && (
                    <div className="mt-2 space-y-1.5">
                      {urlWarn.data.map((w) => (
                        <div
                          key={w.message}
                          className={`flex items-start gap-2 rounded-xl px-3 py-2 text-xs ${w.level === "danger" ? "border border-danger/25 bg-danger/10 text-danger" : "border border-warning/25 bg-warning/10 text-warning"}`}
                        >
                          {w.level === "danger" ? <FishSymbol className="mt-0.5 size-4 shrink-0" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0" />}
                          <span>{w.message}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <label className="flex cursor-pointer items-center justify-between gap-4 rounded-2xl border px-4 py-3">
                  <span className="flex items-center gap-3">
                    <ShieldCheck className="size-5 text-success" />
                    <span>
                      <span className="block text-sm font-medium">Two-factor is on for this account</span>
                      <span className="block text-xs text-muted-foreground">Helps Kavach judge how exposed it really is.</span>
                    </span>
                  </span>
                  <Switch checked={!!form.mfa} disabled={readOnly} onCheckedChange={(c) => setForm((f) => ({ ...f, mfa: c }))} />
                </label>
                {editing && risk && (
                  <div className="rounded-2xl border bg-muted/40 p-4">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Security assessment</div>
                    <EntryRiskCard entry={risk} compact />
                  </div>
                )}
                <Field label="Notes">
                  <div className="relative">
                    <StickyNote className="pointer-events-none absolute left-3.5 top-3.5 size-4 text-muted-foreground" />
                    <Textarea className="pl-10" placeholder="Recovery codes, PINs, who to ask…" value={form.notes ?? ""} onChange={set("notes")} readOnly={readOnly} maxLength={5000} />
                  </div>
                </Field>
              </>
            )}
          </div>

          <div className="flex items-center gap-2 border-t px-6 py-4">
            {editing && canWrite && (
              <Button type="button" variant="ghost" className="text-danger hover:bg-danger/10 hover:text-danger" onClick={() => onDelete(state.entryId!)}>
                <Trash2 /> Delete
              </Button>
            )}
            <div className="ml-auto flex gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                {readOnly ? "Close" : "Cancel"}
              </Button>
              {!readOnly && (
                <Button type="submit" loading={save.isPending} disabled={loading}>
                  <KeyRound /> {editing ? "Save changes" : "Add entry"}
                </Button>
              )}
            </div>
          </div>
        </form>
      </SheetContent>
    </DialogPrimitive.Root>
  );
}
