"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Mail, ShieldCheck, ShieldOff, Smartphone } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { StrengthMeter } from "@/components/strength-meter";
import { Button } from "@/components/ui/button";
import { Field, Input, PasswordInput } from "@/components/ui/input";
import { Avatar, RoleBadge } from "@/components/ui/misc";
import { api, ApiError, type MfaBegin } from "@/lib/api";
import { useStatus } from "@/lib/hooks";
import { copyPlain, formatDateTime, gradientFor, initials } from "@/lib/utils";

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");

function EmailAddress({ email }: { email: string }) {
  const qc = useQueryClient();
  const [value, setValue] = useState(email);
  const [pw, setPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setValue(email), [email]);

  const save = useMutation({
    mutationFn: () => api.setEmail(value.trim(), pw),
    onSuccess: async () => {
      toast.success("Email saved", { description: email ? "We told the old address about the change." : undefined });
      setPw("");
      setError(null);
      await qc.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (e) => setError(errText(e)),
  });

  const changed = value.trim() !== email;
  return (
    <form
      className="glass space-y-4 rounded-3xl p-6"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        save.mutate();
      }}
    >
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Email</h2>
        <p className="text-sm text-muted-foreground">Where Kavach sends security alerts about your account, such as a sign-in from a new address. Changing it needs your master password, and the old address is told.</p>
      </div>
      {error && <p role="alert" className="rounded-xl border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Email address">
          <Input icon={<Mail />} type="email" autoComplete="email" value={value} onChange={(e) => setValue(e.target.value)} placeholder="you@example.com" />
        </Field>
        <Field label="Master password" hint="To confirm it is you.">
          <PasswordInput autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} />
        </Field>
      </div>
      <Button type="submit" loading={save.isPending} disabled={!changed || !pw}>
        Save email
      </Button>
    </form>
  );
}

function ChangePassword({ username, name }: { username: string; name: string }) {
  const [oldPw, setOld] = useState("");
  const [newPw, setNew] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const change = useMutation({
    mutationFn: () => api.changePassword(oldPw, newPw),
    onSuccess: () => {
      toast.success("Password changed", { description: "Your other devices have been signed out." });
      setOld("");
      setNew("");
      setConfirm("");
      setError(null);
    },
    onError: (e) => setError(errText(e)),
  });

  const mismatch = confirm.length > 0 && confirm !== newPw;
  return (
    <form
      className="glass space-y-4 rounded-3xl p-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (mismatch) return setError("The two new passwords don't match.");
        setError(null);
        change.mutate();
      }}
    >
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Master password</h2>
        <p className="text-sm text-muted-foreground">Changing it re-protects your keys; your vaults and their contents are unaffected.</p>
      </div>
      {error && <p role="alert" className="rounded-xl border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
      <Field label="Current password"><PasswordInput autoComplete="current-password" value={oldPw} onChange={(e) => setOld(e.target.value)} required /></Field>
      <Field label="New password"><PasswordInput autoComplete="new-password" value={newPw} onChange={(e) => setNew(e.target.value)} required /></Field>
      <StrengthMeter password={newPw} inputs={[username, name]} />
      <Field label="Confirm new password" error={mismatch ? "The passwords don't match" : undefined}>
        <PasswordInput autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
      </Field>
      <Button type="submit" loading={change.isPending} disabled={!oldPw || !newPw || !confirm}>
        <KeyRound /> Change password
      </Button>
    </form>
  );
}

function TwoFactor({ enabled }: { enabled: boolean }) {
  const qc = useQueryClient();
  const [setup, setSetup] = useState<MfaBegin | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["status"] });

  const begin = useMutation({ mutationFn: api.mfaBegin, onSuccess: (r) => (setSetup(r), setError(null), setCode("")), onError: (e) => setError(errText(e)) });
  const confirm = useMutation({
    mutationFn: () => api.mfaConfirm(code),
    onSuccess: async () => (toast.success("Two-factor is on"), setSetup(null), setCode(""), setError(null), await refresh()),
    onError: (e) => setError(errText(e)),
  });
  const disable = useMutation({
    mutationFn: () => api.mfaDisable(pw, code),
    onSuccess: async () => (toast.success("Two-factor turned off"), setPw(""), setCode(""), setError(null), await refresh()),
    onError: (e) => setError(errText(e)),
  });

  return (
    <div className="glass space-y-4 rounded-3xl p-6">
      <div className="flex items-start gap-4">
        <span className={`flex size-12 shrink-0 items-center justify-center rounded-2xl ${enabled ? "bg-success/15 text-success" : "bg-muted text-muted-foreground"}`}>
          {enabled ? <ShieldCheck className="size-6" /> : <ShieldOff className="size-6" />}
        </span>
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Two-factor authentication</h2>
          <p className="text-sm text-muted-foreground">
            {enabled ? "On. Signing in needs your password and a code from your authenticator app." : "Off. Turn it on so a stolen password alone can't unlock your account."}
          </p>
        </div>
      </div>
      {error && <p role="alert" className="rounded-xl border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}

      {!enabled && !setup && (
        <Button loading={begin.isPending} onClick={() => begin.mutate()}>
          <Smartphone /> Set up two-factor
        </Button>
      )}

      <AnimatePresence>
        {!enabled && setup && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="grid gap-6 rounded-2xl border p-5 sm:grid-cols-[auto_1fr]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={setup.qr} alt="QR code for your authenticator app" width={176} height={176} className="rounded-xl bg-white p-2" />
              <div className="space-y-3">
                <p className="text-sm">
                  <b>1.</b> Scan the code with Google Authenticator, Microsoft Authenticator, Aegis, 1Password… or enter the key by hand:
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 break-all rounded-lg bg-muted px-3 py-2 font-mono text-sm">{setup.secret}</code>
                  <Button variant="ghost" size="icon-sm" aria-label="Copy key" onClick={async () => (await copyPlain(setup.secret), setCopied(true), setTimeout(() => setCopied(false), 1500))}>
                    {copied ? <Check className="text-success" /> : <Copy />}
                  </Button>
                </div>
                <p className="text-sm"><b>2.</b> Enter the 6-digit code it shows:</p>
                <div className="flex gap-2">
                  <Input inputMode="numeric" autoComplete="one-time-code" maxLength={8} placeholder="123 456" value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9 ]/g, ""))} className="max-w-40 font-mono tracking-[0.25em]" aria-label="6-digit code" />
                  <Button loading={confirm.isPending} disabled={code.replace(/\s/g, "").length < 6} onClick={() => confirm.mutate()}>Turn on</Button>
                  <Button variant="ghost" onClick={() => setSetup(null)}>Cancel</Button>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {enabled && (
        <div className="space-y-3 rounded-2xl border p-5">
          <p className="text-sm text-muted-foreground">To turn it off, confirm with your password and a current code.</p>
          <div className="flex flex-wrap gap-2">
            <div className="min-w-48 flex-1"><PasswordInput placeholder="Password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} aria-label="Password" /></div>
            <Input className="max-w-36 font-mono tracking-[0.25em]" inputMode="numeric" maxLength={8} placeholder="123456" value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9 ]/g, ""))} aria-label="6-digit code" />
            <Button variant="outline" className="text-danger" loading={disable.isPending} disabled={!pw || code.replace(/\s/g, "").length < 6} onClick={() => disable.mutate()}>
              Turn off
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AccountPage() {
  const status = useStatus();
  const me = status.data?.me;
  if (!me) return null;
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader title="Account" description="Your profile and how you sign in." />
      <div className="glass flex flex-wrap items-center gap-5 rounded-3xl p-6">
        <Avatar name={me.display_name} gradient={gradientFor(me.username)} className="size-16 rounded-2xl text-xl">
          {initials(me.display_name)}
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="truncate text-2xl font-semibold tracking-tight">{me.display_name}</h2>
            <RoleBadge role={me.role} />
          </div>
          <div className="text-sm text-muted-foreground">@{me.username}{me.email ? ` · ${me.email}` : ""}</div>
        </div>
        <dl className="text-right text-sm">
          <dt className="text-xs uppercase tracking-wider text-muted-foreground">Organisation</dt>
          <dd className="font-medium">{status.data?.org_name}</dd>
          <dt className="mt-2 text-xs uppercase tracking-wider text-muted-foreground">Last sign-in</dt>
          <dd className="font-medium">{formatDateTime(me.last_login)}</dd>
        </dl>
      </div>
      <EmailAddress email={me.email} />
      <TwoFactor enabled={me.totp_enabled} />
      <ChangePassword username={me.username} name={me.display_name} />
    </div>
  );
}
