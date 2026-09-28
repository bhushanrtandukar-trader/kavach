"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Tooltip } from "@/components/ui/tooltip";
import { copyPlain, copySecret, cn } from "@/lib/utils";

const CLEAR_MS = 30_000;

/**
 * Copies a secret fetched on demand, and shows a ring that drains while the clipboard is still
 * holding it (it is wiped after 30 s). The secret is never kept in component state.
 */
export function CopySecretButton({
  fetchSecret,
  label,
  className,
}: {
  fetchSecret: () => Promise<string>;
  label: string;
  className?: string;
}) {
  const [state, setState] = useState<"idle" | "busy" | "copied">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  async function click(e: React.MouseEvent) {
    e.stopPropagation();
    setState("busy");
    try {
      await copySecret(await fetchSecret(), CLEAR_MS);
      setState("copied");
      toast.success(`${label} copied`, { description: "The clipboard clears itself in 30 seconds." });
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setState("idle"), CLEAR_MS);
    } catch {
      setState("idle");
      toast.error(`Couldn't copy ${label.toLowerCase()}`);
    }
  }

  return (
    <Tooltip content={state === "copied" ? "Copied · clearing…" : `Copy ${label.toLowerCase()}`}>
      <button
        onClick={click}
        aria-label={`Copy ${label.toLowerCase()}`}
        disabled={state === "busy"}
        className={cn(
          "relative flex size-8 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-60",
          state === "copied" && "text-success hover:text-success",
          className,
        )}
      >
        {state === "copied" && (
          <svg viewBox="0 0 32 32" className="absolute inset-0 size-full -rotate-90" aria-hidden>
            <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeOpacity="0.18" strokeWidth="2" />
            <circle
              key={Date.now()}
              cx="16"
              cy="16"
              r="14"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              pathLength={100}
              strokeDasharray={100}
              style={{ animation: `ring-drain ${CLEAR_MS}ms linear forwards` }}
            />
          </svg>
        )}
        {state === "copied" ? <Check className="size-4" /> : <Copy className="size-4" />}
      </button>
    </Tooltip>
  );
}

/** For non-secret text (usernames): plain copy with a brief check mark. */
export function CopyTextButton({ text, label, className }: { text: string; label: string; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Tooltip content={done ? "Copied" : `Copy ${label.toLowerCase()}`}>
      <button
        aria-label={`Copy ${label.toLowerCase()}`}
        onClick={async (e) => {
          e.stopPropagation();
          try {
            await copyPlain(text);
            setDone(true);
            setTimeout(() => setDone(false), 1400);
          } catch {
            toast.error("Couldn't copy");
          }
        }}
        className={cn("flex size-7 items-center justify-center rounded-md text-muted-foreground opacity-0 transition hover:bg-muted hover:text-foreground group-hover:opacity-100 focus-visible:opacity-100", done && "opacity-100 text-success", className)}
      >
        {done ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
    </Tooltip>
  );
}
