"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, Building2, KeyRound, Mail, Radar, ShieldCheck, Ticket, User, Users } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Logo } from "@/components/logo";
import { StrengthMeter } from "@/components/strength-meter";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Field, Input, PasswordInput } from "@/components/ui/input";
import { VaultDial } from "@/components/vault-dial";
import { api, ApiError } from "@/lib/api";
import { BRAND } from "@/lib/brand";
import { useStatus } from "@/lib/hooks";

type Mode = "signin" | "activate" | "setup";

const FEATURES = [
  { icon: KeyRound, title: "A key for every vault", text: "Shared with each member by public-key wrapping; admins can manage people without reading secrets." },
  { icon: Users, title: "Real roles, at two levels", text: "Owner, admin, member, auditor — and manager, editor, viewer inside each vault." },
  { icon: Radar, title: "Security that learns", text: "Insights compare every sign-in and copy with what's normal for that person." },
];

function ErrorNote({ message }: { message: string | null }) {
  return (
    <AnimatePresence>
      {message && (
        <motion.div
          initial={{ opacity: 0, y: -6, height: 0 }}
          animate={{ opacity: 1, y: 0, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          role="alert"
          className="overflow-hidden"
        >
          <div className="flex items-start gap-2 rounded-xl border border-danger/25 bg-danger/10 px-3 py-2.5 text-sm text-danger">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{message}</span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function messageOf(e: unknown): string {
  if (e instanceof ApiError) {
    return e.code === "locked_out" && e.retryAfter
      ? `Too many attempts. Try again in ${Math.ceil(e.retryAfter / 60)} min.`
      : e.message;
  }
  return "Something went wrong.";
}

// ───────────────────────── sign in ─────────────────────────
function SignIn({
  onBusy,
  onSuccess,
  initialUsername,
  onSwitch,
}: {
  onBusy: (b: boolean) => void;
  onSuccess: () => void;
  initialUsername: string;
  onSwitch: () => void;
}) {
  const [username, setUsername] = useState(initialUsername);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!username || !password) return setError("Enter your username and password.");
    setLoading(true);
    onBusy(true);
    setError(null);
    try {
      await api.login({ username, password, totp_code: needCode ? code : undefined });
      onSuccess();
    } catch (err) {
      onBusy(false);
      setLoading(false);
      if (err instanceof ApiError && err.code === "mfa_required") {
        setNeedCode(true);
        setError(null);
      } else {
        setError(messageOf(err));
        if (needCode) setCode("");
        else setPassword("");
      }
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <ErrorNote message={error} />
      <Field label="Username">
        <Input icon={<User />} autoFocus value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder="olivia" />
      </Field>
      <Field label="Master password">
        <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" placeholder="••••••••••••" />
      </Field>
      <AnimatePresence>
        {needCode && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <Field label="Authenticator code" hint="From your authenticator app.">
              <Input
                icon={<ShieldCheck />}
                autoFocus
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/[^0-9 ]/g, ""))}
                placeholder="123 456"
                className="font-mono tracking-[0.3em]"
              />
            </Field>
          </motion.div>
        )}
      </AnimatePresence>
      <Button type="submit" size="lg" className="w-full" loading={loading}>
        Unlock <ArrowRight />
      </Button>
      <div className="text-center text-sm text-muted-foreground">
        Have an invite code?{" "}
        <button type="button" onClick={onSwitch} className="font-medium text-primary hover:underline">
          Activate your account
        </button>
      </div>
    </form>
  );
}

// ───────────────────────── activate ─────────────────────────
const activateSchema = z
  .object({
    username: z.string().min(3, "Enter your username"),
    invite_code: z.string().min(10, "Paste the invite code you were given"),
    password: z.string().min(1, "Choose a password"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "The passwords don't match" });

function Activate({ onDone, onSwitch, initial }: { onDone: (username: string) => void; onSwitch: () => void; initial?: { username: string; invite_code: string } }) {
  const { register, handleSubmit, watch, formState } = useForm<z.infer<typeof activateSchema>>({
    resolver: zodResolver(activateSchema),
    defaultValues: initial,
  });
  const [error, setError] = useState<string | null>(null);
  const pw = watch("password") ?? "";

  const submit = handleSubmit(async (v) => {
    setError(null);
    try {
      await api.activate({ username: v.username, invite_code: v.invite_code.trim(), password: v.password });
      toast.success("Account activated", { description: "Sign in with your new master password." });
      onDone(v.username.trim().toLowerCase());
    } catch (e) {
      setError(messageOf(e));
    }
  });

  return (
    <form onSubmit={submit} className="space-y-4">
      <ErrorNote message={error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Username" error={formState.errors.username?.message}>
          <Input icon={<User />} autoComplete="username" {...register("username")} />
        </Field>
        <Field label="Invite code" error={formState.errors.invite_code?.message}>
          <Input icon={<Ticket />} autoComplete="off" spellCheck={false} {...register("invite_code")} />
        </Field>
      </div>
      <Field label="Choose your master password" error={formState.errors.password?.message}>
        <PasswordInput autoComplete="new-password" {...register("password")} />
      </Field>
      <StrengthMeter password={pw} />
      <Field label="Confirm password" error={formState.errors.confirm?.message}>
        <PasswordInput autoComplete="new-password" {...register("confirm")} />
      </Field>
      <p className="rounded-xl bg-muted px-3 py-2 text-xs text-muted-foreground">
        Only you will ever know this password, and it can&apos;t be recovered — an administrator can only reset your
        access, which removes your personal vault.
      </p>
      <Button type="submit" size="lg" className="w-full" loading={formState.isSubmitting}>
        Activate account <ArrowRight />
      </Button>
      <div className="text-center text-sm">
        <button type="button" onClick={onSwitch} className="text-muted-foreground hover:text-foreground">
          ← Back to sign in
        </button>
      </div>
    </form>
  );
}

// ───────────────────────── first-run setup ─────────────────────────
const setupSchema = z
  .object({
    org_name: z.string().min(1, "Give your organisation a name").max(100),
    username: z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{2,31}$/, "3–32 letters, digits, dot, dash or underscore"),
    display_name: z.string().max(80),
    email: z.string().max(320),
    password: z.string().min(1, "Choose a password"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "The passwords don't match" });

function Setup({ onBusy, onSuccess }: { onBusy: (b: boolean) => void; onSuccess: () => void }) {
  const { register, handleSubmit, watch, formState } = useForm<z.infer<typeof setupSchema>>({ resolver: zodResolver(setupSchema) });
  const [error, setError] = useState<string | null>(null);
  const [pw, name, user] = [watch("password") ?? "", watch("display_name") ?? "", watch("username") ?? ""];

  const submit = handleSubmit(async (v) => {
    setError(null);
    onBusy(true);
    try {
      await api.setup({ org_name: v.org_name, username: v.username, display_name: v.display_name, email: v.email, password: v.password });
      onSuccess();
    } catch (e) {
      onBusy(false);
      setError(messageOf(e));
    }
  });

  return (
    <form onSubmit={submit} className="space-y-4">
      <ErrorNote message={error} />
      <Field label="Organisation" error={formState.errors.org_name?.message}>
        <Input icon={<Building2 />} autoFocus placeholder="Acme Ltd" {...register("org_name")} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Username" error={formState.errors.username?.message}>
          <Input icon={<User />} autoComplete="username" placeholder="olivia" {...register("username")} />
        </Field>
        <Field label="Display name">
          <Input placeholder="Olivia Owner" {...register("display_name")} />
        </Field>
      </div>
      <Field label="Email (optional)">
        <Input icon={<Mail />} type="email" autoComplete="email" {...register("email")} />
      </Field>
      <Field label="Master password" error={formState.errors.password?.message}>
        <PasswordInput autoComplete="new-password" {...register("password")} />
      </Field>
      <StrengthMeter password={pw} inputs={[name, user]} />
      <Field label="Confirm password" error={formState.errors.confirm?.message}>
        <PasswordInput autoComplete="new-password" {...register("confirm")} />
      </Field>
      <Button type="submit" size="lg" className="w-full" loading={formState.isSubmitting}>
        Create organisation <ArrowRight />
      </Button>
    </form>
  );
}

// ───────────────────────── page ─────────────────────────
export default function LoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const status = useStatus();
  const [mode, setMode] = useState<Mode>("signin");
  const [busy, setBusy] = useState(false);
  const [unlocked, setUnlocked] = useState(false);
  const [prefill, setPrefill] = useState("");
  const [invite, setInvite] = useState<{ username: string; invite_code: string } | undefined>();

  // The invite email links to /login#activate=<username>:<code>. The fragment never reaches the server; we
  // read it once, fill in the form, and remove it from the address bar and history.
  useEffect(() => {
    const m = /^#activate=([a-z0-9._-]{3,32}):([A-Za-z0-9_-]{10,128})$/i.exec(window.location.hash);
    if (!m) return;
    setInvite({ username: m[1]!.toLowerCase(), invite_code: m[2]! });
    setMode("activate");
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }, []);

  useEffect(() => {
    if (status.data?.me) router.replace("/vaults");
    else if (status.data && !status.data.initialized) setMode("setup");
  }, [status.data, router]);

  function enter() {
    setUnlocked(true);
    setTimeout(async () => {
      await qc.invalidateQueries({ queryKey: ["status"] });
      router.replace("/vaults");
    }, 850);
  }

  const titles: Record<Mode, { h: string; p: string }> = {
    signin: { h: "Welcome back", p: status.data?.org_name ? `Sign in to ${status.data.org_name}` : "Sign in to your vault" },
    activate: { h: "Join your team", p: "Redeem your invite and choose a master password." },
    setup: { h: "Set up Kavach", p: "Create your organisation and its first owner." },
  };

  return (
    <main className="relative grid min-h-dvh overflow-x-clip lg:grid-cols-[1.1fr_1fr]">
      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>

      {/* hero */}
      <section className="relative z-0 hidden flex-col justify-between p-12 lg:flex">
        <Logo />
        <div className="relative z-10 max-w-[30rem]">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass mb-6 inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-medium">
            <ShieldCheck className="size-3.5 text-primary" /> {BRAND.name} · {BRAND.tagline}
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="text-5xl font-semibold leading-[1.05] tracking-tight xl:text-6xl"
          >
            Every secret,
            <br />
            <span className="gradient-text">safely shared.</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }} className="mt-5 max-w-md text-lg text-muted-foreground">
            {BRAND.pitch}
          </motion.p>
          <ul className="mt-9 space-y-4">
            {FEATURES.map(({ icon: Icon, title, text }, i) => (
              <motion.li key={title} initial={{ opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.35 + i * 0.12 }} className="flex gap-3.5">
                <span className="glass flex size-10 shrink-0 items-center justify-center rounded-xl text-primary">
                  <Icon className="size-5" />
                </span>
                <div>
                  <div className="font-medium">{title}</div>
                  <div className="text-sm text-muted-foreground">{text}</div>
                </div>
              </motion.li>
            ))}
          </ul>
        </div>
        <div className="pointer-events-none absolute -right-44 top-1/2 -translate-y-1/2">
          <VaultDial speed={busy ? 6 : 1} unlocked={unlocked} size={420} />
        </div>
        <div className="relative z-10 text-xs text-muted-foreground">Encrypted at rest · Audited · Open source (MIT)</div>
      </section>

      {/* form */}
      <section className="relative z-10 flex items-center justify-center px-5 py-10">
        <motion.div initial={{ opacity: 0, y: 18, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }} className="w-full max-w-md">
          <Logo className="mb-8 lg:hidden" />
          <div className="glass relative overflow-hidden rounded-3xl p-7 sm:p-8">
            <div className="pointer-events-none absolute -right-16 -top-16 size-48 rounded-full bg-primary/20 blur-3xl" />
            <div className="relative mb-6">
              <AnimatePresence mode="wait">
                <motion.div key={mode} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
                  <h2 className="text-2xl font-semibold tracking-tight">{titles[mode].h}</h2>
                  <p className="mt-1 text-sm text-muted-foreground">{titles[mode].p}</p>
                </motion.div>
              </AnimatePresence>
            </div>
            <AnimatePresence mode="wait">
              <motion.div key={mode} initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -18 }} transition={{ duration: 0.22 }} className="relative">
                {status.isLoading ? (
                  <div className="space-y-4">
                    <div className="skeleton h-11" />
                    <div className="skeleton h-11" />
                    <div className="skeleton h-12" />
                  </div>
                ) : status.isError ? (
                  <ErrorNote message={messageOf(status.error)} />
                ) : mode === "signin" ? (
                  <SignIn initialUsername={prefill} onBusy={setBusy} onSuccess={enter} onSwitch={() => setMode("activate")} />
                ) : mode === "activate" ? (
                  <Activate
                    initial={invite}
                    onSwitch={() => setMode("signin")}
                    onDone={(u) => {
                      setPrefill(u);
                      setMode("signin");
                    }}
                  />
                ) : (
                  <Setup onBusy={setBusy} onSuccess={enter} />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
          <p className="mt-6 text-center text-xs text-muted-foreground">
            Your master password never leaves your control. Lose it and your data is unrecoverable — by design.
          </p>
        </motion.div>
      </section>
    </main>
  );
}
