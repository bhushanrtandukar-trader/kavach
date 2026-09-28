"use client";

import * as PopoverPrimitive from "@radix-ui/react-popover";
import { useMutation } from "@tanstack/react-query";
import { RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Slider, Switch } from "@/components/ui/controls";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Digits and symbols get their own colours so a generated password is easy to read aloud or check. */
function Colored({ text }: { text: string }) {
  return (
    <>
      {[...text].map((c, i) => (
        <span key={i} className={cn(/[0-9]/.test(c) ? "text-accent" : /[^a-zA-Z0-9]/.test(c) ? "text-primary-2" : "")}>
          {c}
        </span>
      ))}
    </>
  );
}

export function PasswordGenerator({ onUse }: { onUse: (password: string) => void }) {
  const [open, setOpen] = useState(false);
  const [length, setLength] = useState(20);
  const [digits, setDigits] = useState(true);
  const [symbols, setSymbols] = useState(true);
  const [readable, setReadable] = useState(false);
  const [preview, setPreview] = useState("");

  const gen = useMutation({
    mutationFn: () => api.generate({ length, digits, symbols, ambiguous: !readable }),
    onSuccess: (r) => setPreview(r.password),
  });

  useEffect(() => {
    if (open) gen.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, length, digits, symbols, readable]);

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Trigger asChild>
        <Button type="button" variant="soft" size="sm">
          <Sparkles /> Generate
        </Button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content align="end" sideOffset={8} className="anim-menu glass-solid z-[80] w-[22rem] rounded-2xl p-4 outline-none">
          <div className="mb-4 flex items-start gap-2 rounded-xl bg-muted p-3">
            <code className="min-h-6 flex-1 break-all font-mono text-[15px] leading-relaxed">
              {preview ? <Colored text={preview} /> : <span className="skeleton inline-block h-5 w-full" />}
            </code>
            <button type="button" aria-label="Regenerate" onClick={() => gen.mutate()} className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-background hover:text-foreground">
              <RefreshCw className={cn("size-4", gen.isPending && "animate-spin")} />
            </button>
          </div>
          <div className="mb-4 space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Length</span>
              <span className="font-mono font-medium tabular-nums">{length}</span>
            </div>
            <Slider min={8} max={64} step={1} value={[length]} onValueChange={(v) => setLength(v[0] ?? 20)} aria-label="Password length" />
          </div>
          <div className="mb-4 space-y-2.5 text-sm">
            {(
              [
                ["Numbers", digits, setDigits],
                ["Symbols", symbols, setSymbols],
                ["Easy to read aloud", readable, setReadable],
              ] as const
            ).map(([label, value, set]) => (
              <label key={label} className="flex cursor-pointer items-center justify-between">
                <span>{label}</span>
                <Switch checked={value} onCheckedChange={set} />
              </label>
            ))}
          </div>
          <Button
            type="button"
            className="w-full"
            disabled={!preview}
            onClick={() => {
              onUse(preview);
              setOpen(false);
            }}
          >
            Use this password
          </Button>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
