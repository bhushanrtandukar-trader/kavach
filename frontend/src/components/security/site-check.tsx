"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Globe, HelpCircle, OctagonAlert, ShieldAlert, ShieldCheck } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { ServiceAvatar, RiskBar } from "@/components/security/parts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type SiteCheck } from "@/lib/api";
import { decisionOf, LEVEL } from "@/lib/intel";
import { cn } from "@/lib/utils";

const TONE = {
  success: { color: "var(--success)", icon: ShieldCheck },
  warning: { color: "var(--warning)", icon: ShieldAlert },
  danger: { color: "var(--danger)", icon: OctagonAlert },
  neutral: { color: "var(--muted-foreground)", icon: HelpCircle },
};

/** Would Kavach autofill on this page? The decision a browser extension would ask for, made from the URL alone. */
export function SiteCheckPanel({ examples }: { examples: string[] }) {
  const [url, setUrl] = useState("");
  const check = useMutation<SiteCheck, ApiError, string>({ mutationFn: (u) => api.siteCheck(u) });
  const res = check.data;
  const dec = res ? decisionOf(res.decision) : null;
  const tone = dec ? TONE[dec.tone] : null;

  return (
    <div className="space-y-5">
      <form
        className="glass flex flex-wrap gap-3 rounded-3xl p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (url.trim()) check.mutate(url.trim());
        }}
      >
        <div className="min-w-64 flex-1">
          <Input icon={<Globe />} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste a link, e.g. https://paypa1.com/login" aria-label="Address to check" />
        </div>
        <Button type="submit" loading={check.isPending} disabled={!url.trim()}>
          Check this site
        </Button>
        <div className="flex w-full flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          Try:
          {examples.map((ex) => (
            <button
              type="button"
              key={ex}
              onClick={() => {
                setUrl(ex);
                check.mutate(ex);
              }}
              className="rounded-full border px-2.5 py-0.5 transition hover:border-primary/40 hover:text-foreground"
            >
              {ex}
            </button>
          ))}
        </div>
      </form>

      {check.isError && <p role="alert" className="rounded-xl border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">{check.error.message}</p>}

      <AnimatePresence mode="wait">
        {res && tone && (
          <motion.div key={res.url} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="glass overflow-hidden rounded-3xl">
            <div className="flex flex-wrap items-center gap-4 border-b p-5" style={{ background: `color-mix(in oklab, ${tone.color} 9%, transparent)` }}>
              <span className="flex size-14 items-center justify-center rounded-2xl text-white" style={{ background: tone.color }}>
                <tone.icon className="size-7" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-xl font-semibold tracking-tight" style={{ color: tone.color }}>{dec?.label}</div>
                <div className="truncate text-sm text-muted-foreground">{res.domain || res.url}</div>
              </div>
              <div className="w-48">
                <div className="mb-1 flex justify-between text-xs">
                  <span className="text-muted-foreground">Phishing risk</span>
                  <b className="tabular-nums" style={{ color: LEVEL[res.level]?.color }}>{res.risk}/100</b>
                </div>
                <RiskBar risk={res.risk} level={res.level} />
              </div>
            </div>
            <div className="grid gap-6 p-5 md:grid-cols-2">
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Why</h4>
                <ul className="space-y-2 text-sm">
                  {res.reasons.map((r, i) => (
                    <li key={i} className="flex gap-2">
                      <CheckCircle2 className={cn("mt-0.5 size-4 shrink-0", res.decision === "block" ? "text-danger" : "text-muted-foreground")} />
                      <span>{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="space-y-4">
                {res.impersonates.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-danger">Imitates your saved login</h4>
                    {res.impersonates.map((m) => (
                      <div key={m.id} className="flex items-center gap-2.5 text-sm"><ServiceAvatar service={m.service} className="size-8" /> {m.service}</div>
                    ))}
                  </div>
                )}
                {res.matches.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Matches your saved login</h4>
                    {res.matches.map((m) => (
                      <div key={m.id} className="flex items-center gap-2.5 text-sm"><ServiceAvatar service={m.service} className="size-8" /> {m.service} <span className="text-xs text-muted-foreground">· {m.username}</span></div>
                    ))}
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  Based on the address alone, checked on this server. It can&apos;t see a site&apos;s age, certificate or redirects. A browser extension would ask this same question before every autofill.
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
