"use client";

import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const badge = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide transition-colors",
  {
    variants: {
      tone: {
        neutral: "border-transparent bg-muted text-muted-foreground",
        primary: "border-transparent bg-primary/12 text-primary",
        success: "border-transparent bg-success/14 text-success",
        warning: "border-transparent bg-warning/16 text-warning",
        danger: "border-transparent bg-danger/14 text-danger",
        accent: "border-transparent bg-accent/15 text-accent",
        outline: "text-muted-foreground",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ tone }), className)} {...props} />;
}

const ROLE_TONE: Record<string, VariantProps<typeof badge>["tone"]> = {
  owner: "warning",
  admin: "danger",
  member: "primary",
  auditor: "accent",
  manager: "warning",
  editor: "success",
  viewer: "neutral",
};

export function RoleBadge({ role, className }: { role: string; className?: string }) {
  return (
    <Badge tone={ROLE_TONE[role] ?? "neutral"} className={className}>
      {role}
    </Badge>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-md border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass rounded-2xl", className)} {...props} />;
}

export function Separator({ className }: { className?: string }) {
  return <div role="separator" className={cn("h-px w-full bg-border", className)} />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-16 text-center", className)}>
      <div className="relative mb-5">
        <div className="absolute inset-0 rounded-3xl bg-primary/25 blur-2xl" />
        <div className="gradient-bg relative flex size-16 animate-float items-center justify-center rounded-3xl text-white shadow-lg [&_svg]:size-7">
          {icon}
        </div>
      </div>
      <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Avatar({
  name,
  gradient,
  className,
  children,
}: {
  name: string;
  gradient: string;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <span
      title={name}
      style={{ background: gradient }}
      className={cn(
        "inline-flex size-9 shrink-0 select-none items-center justify-center rounded-xl text-xs font-bold text-white shadow-sm ring-1 ring-white/10",
        className,
      )}
    >
      {children}
    </span>
  );
}
