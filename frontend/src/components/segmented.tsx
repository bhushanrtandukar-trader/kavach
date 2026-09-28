"use client";

import { motion } from "motion/react";
import { useId } from "react";
import { cn } from "@/lib/utils";

/** A pill tab bar whose highlight glides between options. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: React.ReactNode }[];
  className?: string;
}) {
  const id = useId();
  return (
    <div role="tablist" className={cn("glass inline-flex rounded-xl p-1 text-sm", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn("relative rounded-lg px-4 py-1.5 font-medium transition-colors", value === o.value ? "text-foreground" : "text-muted-foreground hover:text-foreground")}
        >
          {value === o.value && <motion.span layoutId={`seg-${id}`} className="absolute inset-0 rounded-lg bg-primary/15 ring-1 ring-primary/30" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
          <span className="relative flex items-center gap-2">{o.label}</span>
        </button>
      ))}
    </div>
  );
}
