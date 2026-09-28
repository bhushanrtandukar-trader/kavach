"use client";

import { animate, motion } from "motion/react";
import { useEffect, useState } from "react";

const TONE: Record<string, string> = {
  success: "var(--success)",
  info: "var(--accent)",
  warning: "var(--warning)",
  danger: "var(--danger)",
};

/** A score dial: the arc sweeps in and the number counts up. Colour follows the verdict. */
export function HealthRing({ score, label, color, size = 220 }: { score: number; label: string; color: string; size?: number }) {
  const [shown, setShown] = useState(0);
  const r = 88;
  const c = 2 * Math.PI * r;
  const tone = TONE[color] ?? "var(--primary)";

  useEffect(() => {
    const controls = animate(0, score, { duration: 1.3, ease: [0.22, 1, 0.36, 1], onUpdate: (v) => setShown(Math.round(v)) });
    return () => controls.stop();
  }, [score]);

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <div className="absolute inset-4 rounded-full blur-2xl" style={{ background: tone, opacity: 0.22 }} />
      <svg viewBox="0 0 200 200" className="relative size-full -rotate-90">
        <defs>
          <linearGradient id="ring-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={tone} />
            <stop offset="1" stopColor="var(--primary-2)" />
          </linearGradient>
        </defs>
        <circle cx="100" cy="100" r={r} fill="none" stroke="var(--muted)" strokeWidth="14" />
        <motion.circle
          cx="100"
          cy="100"
          r={r}
          fill="none"
          stroke="url(#ring-g)"
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - score / 100) }}
          transition={{ duration: 1.3, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-6xl font-semibold tabular-nums tracking-tight">{shown}</div>
        <div className="mt-1 text-sm font-semibold" style={{ color: tone }}>
          {label}
        </div>
      </div>
    </div>
  );
}
