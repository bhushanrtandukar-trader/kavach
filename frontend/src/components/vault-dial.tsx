"use client";

import { motion } from "motion/react";
import { useId } from "react";

/**
 * The brand mark, drawn large: a combination-lock dial whose rings turn against each other.
 * `speed` 1 = idle; the sign-in form raises it while a request is in flight and `unlocked` opens the ring.
 */
export function VaultDial({ speed = 1, unlocked = false, size = 340 }: { speed?: number; unlocked?: boolean; size?: number }) {
  const id = useId();
  const ticks = Array.from({ length: 60 }, (_, i) => i);
  const dur = (s: number) => s / Math.max(speed, 0.2);

  return (
    <div className="relative animate-float" style={{ width: size, height: size }}>
      <div className="absolute inset-6 rounded-full bg-primary/30 blur-3xl" />
      <svg viewBox="0 0 340 340" className="relative size-full drop-shadow-[0_20px_50px_rgba(107,70,255,0.35)]">
        <defs>
          <linearGradient id={`${id}-g`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--primary)" />
            <stop offset="0.55" stopColor="var(--primary-2)" />
            <stop offset="1" stopColor="var(--accent)" />
          </linearGradient>
          <radialGradient id={`${id}-face`} cx="0.35" cy="0.3" r="0.9">
            <stop offset="0" stopColor="color-mix(in oklab, var(--card-solid) 80%, white 20%)" />
            <stop offset="1" stopColor="var(--card-solid)" />
          </radialGradient>
        </defs>

        {/* outer bezel */}
        <circle cx="170" cy="170" r="160" fill={`url(#${id}-face)`} stroke={`url(#${id}-g)`} strokeWidth="2.5" />
        <circle cx="170" cy="170" r="150" fill="none" stroke="var(--border)" strokeWidth="1" />

        {/* tick ring, turns slowly one way */}
        <motion.g
          style={{ transformOrigin: "50% 50%", transformBox: "view-box" }}
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, ease: "linear", duration: dur(80) }}
        >
          {ticks.map((i) => {
            const major = i % 5 === 0;
            return (
              <line
                key={i}
                x1="170"
                y1={major ? 22 : 26}
                x2="170"
                y2="34"
                stroke={major ? `url(#${id}-g)` : "var(--muted-foreground)"}
                strokeOpacity={major ? 1 : 0.45}
                strokeWidth={major ? 2.5 : 1.2}
                strokeLinecap="round"
                transform={`rotate(${i * 6} 170 170)`}
              />
            );
          })}
        </motion.g>

        {/* middle ring, counter-rotating, with a gap that "opens" when unlocked */}
        <motion.g
          style={{ transformOrigin: "50% 50%", transformBox: "view-box" }}
          animate={{ rotate: -360 }}
          transition={{ repeat: Infinity, ease: "linear", duration: dur(55) }}
        >
          <motion.circle
            cx="170"
            cy="170"
            r="108"
            fill="none"
            stroke={`url(#${id}-g)`}
            strokeWidth="9"
            strokeLinecap="round"
            initial={false}
            animate={{ strokeDasharray: unlocked ? "540 140" : "600 80", opacity: unlocked ? 1 : 0.9 }}
            transition={{ duration: 0.8, ease: "easeInOut" }}
          />
          {[0, 90, 180, 270].map((a) => (
            <circle key={a} cx="170" cy="62" r="4.5" fill="var(--card-solid)" stroke={`url(#${id}-g)`} strokeWidth="2" transform={`rotate(${a} 170 170)`} />
          ))}
        </motion.g>

        {/* inner dial */}
        <motion.g
          style={{ transformOrigin: "50% 50%", transformBox: "view-box" }}
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, ease: "linear", duration: dur(34) }}
        >
          <circle cx="170" cy="170" r="76" fill="none" stroke="var(--border)" strokeWidth="1.5" strokeDasharray="2 7" />
        </motion.g>
        <circle cx="170" cy="170" r="58" fill={`url(#${id}-g)`} />
        <circle cx="170" cy="170" r="58" fill="none" stroke="white" strokeOpacity="0.25" strokeWidth="1.5" />

        {/* keyhole → open shackle */}
        <motion.path
          d="M150 168v-12a20 20 0 0 1 40 0v12"
          fill="none"
          stroke="white"
          strokeWidth="6"
          strokeLinecap="round"
          initial={false}
          animate={{ y: unlocked ? -9 : 0, rotate: unlocked ? -18 : 0 }}
          style={{ transformOrigin: "0% 100%", transformBox: "fill-box" }}
          transition={{ type: "spring", stiffness: 160, damping: 14 }}
        />
        <rect x="142" y="166" width="56" height="40" rx="10" fill="white" />
        <circle cx="170" cy="183" r="5" fill="var(--primary)" />
        <rect x="167.5" y="184" width="5" height="12" rx="2.5" fill="var(--primary)" />
      </svg>
    </div>
  );
}
