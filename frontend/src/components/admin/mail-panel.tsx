"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Mail, MailWarning, Send, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { api, ApiError } from "@/lib/api";
import { relativeTime } from "@/lib/utils";

const KIND_LABEL: Record<string, string> = {
  invite: "Invite",
  test: "Test email",
  digest: "Weekly digest",
  "alert.new_signin": "New sign-in alert",
  "alert.locked": "Lockout alert",
  "alert.password_changed": "Password-change alert",
  "alert.mfa_enabled": "Two-factor on",
  "alert.mfa_disabled": "Two-factor off",
  "alert.mfa_reset": "Two-factor reset",
  "alert.email_changed": "Email-change alert",
};

/** Whether the server can send email, a test button, and how the last few messages went. */
export function MailPanel({ hasEmail }: { hasEmail: boolean }) {
  const qc = useQueryClient();
  const mail = useQuery({ queryKey: ["mail"], queryFn: api.mail });
  const test = useMutation({
    mutationFn: api.testMail,
    onSuccess: async () => {
      toast.success("Test email sent", { description: "Check your inbox (and spam folder)." });
      await qc.invalidateQueries({ queryKey: ["mail"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not send the test email."),
  });

  if (mail.isLoading || !mail.data) return <Skeleton className="h-48" />;
  const m = mail.data;

  return (
    <div className="glass rounded-3xl p-6">
      <div className="flex flex-wrap items-start gap-4">
        <span className={`flex size-12 shrink-0 items-center justify-center rounded-2xl ${m.configured ? "bg-success/15 text-success" : "bg-muted text-muted-foreground"}`}>
          {m.configured ? <Mail className="size-6" /> : <MailWarning className="size-6" />}
        </span>
        <div className="min-w-0 flex-1 basis-64">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold tracking-tight">Email delivery</h2>
            <Badge tone={m.configured ? "success" : "neutral"}>{m.configured ? "on" : "not set up"}</Badge>
          </div>
          {m.configured ? (
            <p className="text-sm text-muted-foreground">
              Sending as <b className="font-medium text-foreground">{m.sender}</b> through {m.host}:{m.port} ({m.security === "none" ? "no encryption" : m.security.toUpperCase()}). Links in emails point to {m.public_url}.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Kavach can email invites, security alerts and a weekly digest. It is set up by the person who runs the server, with environment variables:{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs">KAVACH_SMTP_HOST</code>,{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs">KAVACH_MAIL_FROM</code> and, if your server needs a login,{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs">KAVACH_SMTP_USER</code> /{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs">KAVACH_SMTP_PASSWORD</code>. See the README.
            </p>
          )}
        </div>
        {m.configured && (
          <Button variant="outline" loading={test.isPending} disabled={!hasEmail} onClick={() => test.mutate()} title={hasEmail ? undefined : "Add an email address to your account first"}>
            <Send /> Send me a test
          </Button>
        )}
      </div>

      {m.configured && !hasEmail && (
        <p className="mt-4 rounded-xl bg-muted px-3 py-2 text-xs text-muted-foreground">Add an email address on the Account page to receive the test message.</p>
      )}

      {m.recent.length > 0 && (
        <div className="mt-5">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Recent messages</div>
          <ul className="divide-y rounded-2xl border">
            {m.recent.map((e, i) => (
              <li key={`${e.ts}-${i}`} className="flex items-start gap-3 px-4 py-2.5 text-sm">
                {e.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-danger" />}
                <div className="min-w-0 flex-1">
                  <div className="truncate">
                    {KIND_LABEL[e.kind] ?? e.kind} <span className="text-muted-foreground">→ {e.to}</span>
                  </div>
                  {!e.ok && e.error && <div className="text-xs text-danger">{e.error}</div>}
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">{relativeTime(e.ts)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
