"use client";

import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { api } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const TONES = [
  { label: "Very weak", color: "var(--danger)" },
  { label: "Weak", color: "var(--danger)" },
  { label: "Fair", color: "var(--warning)" },
  { label: "Strong", color: "var(--accent)" },
  { label: "Very strong", color: "var(--success)" },
];

/** Live password-strength readout: five segments, a verdict and, when it helps, a reason. */
export function StrengthMeter({
  password,
  inputs = [],
  className,
  compact,
}: {
  password: string;
  inputs?: string[];
  className?: string;
  compact?: boolean;
}) {
  const debounced = useDebounced(password, 220);
  const { data } = useQuery({
    queryKey: ["strength", debounced, inputs.join("|")],
    queryFn: () => api.strength(debounced, inputs),
    enabled: debounced.length > 0,
    staleTime: Infinity,
    placeholderData: (prev) => prev,
  });

  if (!password) return <div className={cn("h-5", className)} />;
  const score = data && debounced === password ? data.score : (data?.score ?? 0);
  const tone = TONES[score] ?? TONES[0]!;

  return (
    <div className={cn("space-y-1.5", className)} aria-live="polite">
      <div className="flex gap-1.5">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
            <motion.div
              className="h-full rounded-full"
              initial={false}
              animate={{ width: data && i <= score ? "100%" : "0%", backgroundColor: tone.color }}
              transition={{ duration: 0.35, delay: i * 0.04, ease: "easeOut" }}
            />
          </div>
        ))}
      </div>
      <AnimatePresence mode="wait">
        {data && (
          <motion.div
            key={score + (data.warning || "")}
            initial={{ opacity: 0, y: -3 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex flex-wrap items-baseline justify-between gap-x-3 text-xs"
          >
            <span className="font-semibold" style={{ color: tone.color }}>
              {tone.label}
            </span>
            {!compact && (
              <span className="text-muted-foreground">
                {data.warning || (data.suggestions[0] ?? `Offline crack time: ${data.crack_time}`)}
              </span>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
