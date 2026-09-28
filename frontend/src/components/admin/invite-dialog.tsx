"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Mail, Send, User, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/menu";
import { api, ApiError, type Invite, type OrgRole } from "@/lib/api";
import { copyPlain } from "@/lib/utils";

const ROLE_HELP: Record<OrgRole, string> = {
  owner: "Full control, including appointing admins.",
  admin: "Manages people, policy and the audit log. Cannot read vaults they aren't in.",
  member: "Has a personal vault; can create and join shared vaults.",
  auditor: "Read-only access to the audit log and people list. No vaults.",
};

/** Shown after an invite is created or re-issued. The code cannot be retrieved again. */
export function InviteCard({ invite, orgName }: { invite: Invite; orgName: string }) {
  const [copied, setCopied] = useState<"code" | "msg" | null>(null);
  const url = typeof window !== "undefined" ? `${window.location.origin}/login` : "/login";
  const message =
    `Hi! You've been invited to ${orgName} on Guptakosh.\n\n` +
    `1. Open ${url}\n2. Choose "Activate your account"\n3. Username: ${invite.username}\n4. Invite code: ${invite.invite_code}\n\n` +
    `The code works once and expires in ${invite.valid_hours} hours. You'll choose your own master password.`;

  async function copy(what: "code" | "msg") {
    await copyPlain(what === "code" ? invite.invite_code : message);
    setCopied(what);
    setTimeout(() => setCopied(null), 1800);
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-success/25 bg-success/8 p-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-success">Invite code for @{invite.username}</div>
        <div className="flex items-center gap-2">
          <code className="flex-1 select-all break-all rounded-xl bg-background/60 px-3 py-2.5 font-mono text-[15px]">{invite.invite_code}</code>
          <Button variant="secondary" size="icon" aria-label="Copy code" onClick={() => void copy("code")}>
            {copied === "code" ? <Check className="text-success" /> : <Copy />}
          </Button>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        This is the only time the code is shown. Send it privately. It works once and is valid for {invite.valid_hours} hours.
      </p>
      <Button variant="outline" className="w-full" onClick={() => void copy("msg")}>
        {copied === "msg" ? <Check className="text-success" /> : <Send />} Copy a ready-to-send message
      </Button>
    </div>
  );
}

export function InviteDialog({ open, onOpenChange, assignable, orgName }: { open: boolean; onOpenChange: (o: boolean) => void; assignable: OrgRole[]; orgName: string }) {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [display, setDisplay] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrgRole>("member");
  const [error, setError] = useState<string | null>(null);
  const [invite, setInvite] = useState<Invite | null>(null);

  useEffect(() => {
    if (open) {
      setUsername("");
      setDisplay("");
      setEmail("");
      setRole("member");
      setError(null);
      setInvite(null);
    }
  }, [open]);

  const create = useMutation({
    mutationFn: () => api.invite({ username, display_name: display, email, role }),
    onSuccess: async (r) => {
      setInvite(r);
      toast.success(`Invite created for @${r.username}`);
      await qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not create the invite."),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <div className="gradient-bg mb-2 flex size-12 items-center justify-center rounded-2xl text-white">
            <UserPlus className="size-6" />
          </div>
          <DialogTitle>{invite ? "Invite ready" : "Invite someone"}</DialogTitle>
          <DialogDescription>
            {invite ? "Give them this code; they'll set their own password." : "They choose their own master password, so nobody else ever knows it."}
          </DialogDescription>
        </DialogHeader>
        {invite ? (
          <>
            <InviteCard invite={invite} orgName={orgName} />
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              create.mutate();
            }}
          >
            {error && <p role="alert" className="rounded-xl border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Username">
                <Input icon={<User />} autoFocus value={username} onChange={(e) => setUsername(e.target.value)} placeholder="mia" required />
              </Field>
              <Field label="Display name">
                <Input value={display} onChange={(e) => setDisplay(e.target.value)} placeholder="Mia Member" />
              </Field>
            </div>
            <Field label="Email (optional)" hint="Only for your own records; Guptakosh doesn't send email.">
              <Input icon={<Mail />} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Role" hint={ROLE_HELP[role]}>
              <Select value={role} onValueChange={(v) => setRole(v as OrgRole)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {assignable.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r[0]!.toUpperCase() + r.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={create.isPending} disabled={!username.trim()}>
                Create invite
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
