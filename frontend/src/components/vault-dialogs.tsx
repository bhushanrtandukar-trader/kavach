"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut, Plus, Trash2, UserPlus, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/menu";
import { Avatar, RoleBadge, Skeleton } from "@/components/ui/misc";
import { api, ApiError, type Vault, type VaultRole } from "@/lib/api";
import { useStatus } from "@/lib/hooks";
import { gradientFor, initials } from "@/lib/utils";

const ROLES: { value: VaultRole; label: string; hint: string }[] = [
  { value: "manager", label: "Manager", hint: "Everything, including who has access" },
  { value: "editor", label: "Editor", hint: "Add, edit and delete entries" },
  { value: "viewer", label: "Viewer", hint: "Read and copy passwords" },
];

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");

function RoleSelect({ value, onChange, disabled }: { value: VaultRole; onChange: (r: VaultRole) => void; disabled?: boolean }) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as VaultRole)} disabled={disabled}>
      <SelectTrigger className="h-9 w-32 text-[13px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {ROLES.map((r) => (
          <SelectItem key={r.value} value={r.value}>
            {r.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// ───────────────────────── new vault ─────────────────────────
export function NewVaultDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (id: string) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName("");
      setDescription("");
      setError(null);
    }
  }, [open]);

  const create = useMutation({
    mutationFn: () => api.createVault(name, description),
    onSuccess: async (r) => {
      await qc.invalidateQueries({ queryKey: ["vaults"] });
      toast.success("Vault created", { description: "You are its manager. Add people from the Access button." });
      onOpenChange(false);
      onCreated(r.id);
    },
    onError: (e) => setError(errMsg(e)),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <DialogHeader>
            <div className="gradient-bg mb-2 flex size-12 items-center justify-center rounded-2xl text-white">
              <Plus className="size-6" />
            </div>
            <DialogTitle>New shared vault</DialogTitle>
            <DialogDescription>A vault has its own encryption key and its own list of people, so you decide exactly who can see what.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {error && <p className="rounded-xl border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
            <Field label="Name">
              <Input autoFocus placeholder="e.g. Infrastructure" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required />
            </Field>
            <Field label="Description (optional)">
              <Input placeholder="What lives here?" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} />
            </Field>
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
              Create vault
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ───────────────────────── access dialog ─────────────────────────
export function AccessDialog({ vault, open, onOpenChange, onGone }: { vault: Vault; open: boolean; onOpenChange: (o: boolean) => void; onGone: () => void }) {
  const qc = useQueryClient();
  const me = useStatus().data?.me;
  const isManager = vault.role === "manager";
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [addUser, setAddUser] = useState("");
  const [addRole, setAddRole] = useState<VaultRole>("viewer");
  const [name, setName] = useState(vault.name);
  const [description, setDescription] = useState(vault.description);

  useEffect(() => {
    if (open) {
      setName(vault.name);
      setDescription(vault.description);
      setAddUser("");
    }
  }, [open, vault.name, vault.description]);

  const members = useQuery({ queryKey: ["members", vault.id], queryFn: () => api.members(vault.id), enabled: open });
  const directory = useQuery({ queryKey: ["directory"], queryFn: api.directory, enabled: open && isManager });
  const candidates = (directory.data ?? []).filter((u) => !(members.data ?? []).some((m) => m.user_id === u.id));

  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ["members", vault.id] }), qc.invalidateQueries({ queryKey: ["vaults"] })]);
  const fail = (e: unknown) => toast.error(errMsg(e));

  const add = useMutation({
    mutationFn: () => api.addMember(vault.id, addUser, addRole),
    onSuccess: async () => {
      setAddUser("");
      toast.success("Access granted");
      await refresh();
    },
    onError: fail,
  });
  const setRole = useMutation({
    mutationFn: (v: { id: string; role: VaultRole }) => api.setMemberRole(vault.id, v.id, v.role),
    onSuccess: refresh,
    onError: (e) => (fail(e), refresh()),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.removeMember(vault.id, id),
    onSuccess: async (_, id) => {
      toast.success("Removed. The vault key was replaced so they cannot read anything new.");
      await refresh();
      if (id === me?.id) {
        onOpenChange(false);
        onGone();
      }
    },
    onError: fail,
  });
  const save = useMutation({
    mutationFn: () => api.updateVault(vault.id, name, description),
    onSuccess: async () => (toast.success("Vault updated"), refresh()),
    onError: fail,
  });
  const del = useMutation({
    mutationFn: () => api.deleteVault(vault.id),
    onSuccess: async () => {
      toast.success("Vault deleted");
      setConfirmDelete(false);
      onOpenChange(false);
      await qc.invalidateQueries({ queryKey: ["vaults"] });
      onGone();
    },
    onError: fail,
  });

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <div className="gradient-bg mb-2 flex size-12 items-center justify-center rounded-2xl text-white">
              <Users className="size-6" />
            </div>
            <DialogTitle>Access to {vault.name}</DialogTitle>
            <DialogDescription>
              Everyone here can open this vault; what they can do depends on their role.
              {!isManager && " Only managers can change access."}
            </DialogDescription>
          </DialogHeader>

          <ul className="space-y-1">
            {members.isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-14" />)}
            {(members.data ?? []).map((m) => (
              <li key={m.user_id} className="flex items-center gap-3 rounded-2xl px-2 py-2 hover:bg-muted/60">
                <Avatar name={m.display_name} gradient={gradientFor(m.username)}>
                  {initials(m.display_name)}
                </Avatar>
                <div className="min-w-0 flex-1 leading-tight">
                  <div className="truncate text-sm font-medium">
                    {m.display_name} {m.user_id === me?.id && <span className="text-xs font-normal text-muted-foreground">(you)</span>}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">@{m.username}</div>
                </div>
                {isManager ? (
                  <>
                    <RoleSelect value={m.role as VaultRole} onChange={(role) => setRole.mutate({ id: m.user_id, role })} />
                    <Button variant="ghost" size="icon-sm" aria-label={`Remove ${m.username}`} className="text-muted-foreground hover:text-danger" onClick={() => remove.mutate(m.user_id)}>
                      <Trash2 />
                    </Button>
                  </>
                ) : (
                  <RoleBadge role={m.role} />
                )}
              </li>
            ))}
          </ul>

          {isManager && (
            <div className="mt-5 space-y-5 border-t pt-5">
              <div>
                <div className="mb-2 text-sm font-medium">Add someone</div>
                <div className="flex flex-wrap gap-2">
                  <div className="min-w-44 flex-1">
                    <Select value={addUser} onValueChange={setAddUser}>
                      <SelectTrigger className="h-10">
                        <SelectValue placeholder={candidates.length ? "Choose a person…" : "Everyone already has access"} />
                      </SelectTrigger>
                      <SelectContent>
                        {candidates.map((u) => (
                          <SelectItem key={u.id} value={u.id}>
                            {u.display_name} (@{u.username})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <RoleSelect value={addRole} onChange={setAddRole} />
                  <Button disabled={!addUser} loading={add.isPending} onClick={() => add.mutate()}>
                    <UserPlus /> Add
                  </Button>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">{ROLES.find((r) => r.value === addRole)?.hint}. People must have activated their account first.</p>
              </div>

              <div>
                <div className="mb-2 text-sm font-medium">Details</div>
                <div className="flex flex-wrap gap-2">
                  <Input className="min-w-40 flex-1" value={name} onChange={(e) => setName(e.target.value)} aria-label="Vault name" />
                  <Input className="min-w-40 flex-[2]" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" aria-label="Description" />
                  <Button variant="secondary" loading={save.isPending} disabled={!name.trim() || (name === vault.name && description === vault.description)} onClick={() => save.mutate()}>
                    Save
                  </Button>
                </div>
              </div>
            </div>
          )}

          <DialogFooter className="mt-6 sm:justify-between">
            {isManager ? (
              <Button variant="ghost" className="text-danger hover:bg-danger/10 hover:text-danger" onClick={() => setConfirmDelete(true)}>
                <Trash2 /> Delete vault
              </Button>
            ) : (
              <Button variant="ghost" onClick={() => setConfirmLeave(true)}>
                <LogOut /> Leave vault
              </Button>
            )}
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete “${vault.name}”?`}
        description={`This permanently deletes the vault and all ${vault.entry_count} entries in it, for everyone. It cannot be undone.`}
        confirmLabel="Delete vault"
        loading={del.isPending}
        onConfirm={() => del.mutate()}
      />
      <ConfirmDialog
        open={confirmLeave}
        onOpenChange={setConfirmLeave}
        title={`Leave “${vault.name}”?`}
        description="You will lose access to everything in it until a manager adds you again."
        confirmLabel="Leave"
        destructive={false}
        loading={remove.isPending}
        onConfirm={() => me && remove.mutate(me.id, { onSettled: () => setConfirmLeave(false) })}
      />
    </>
  );
}
