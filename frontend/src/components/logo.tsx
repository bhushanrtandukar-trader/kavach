import { BRAND } from "@/lib/brand";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "gradient-bg relative inline-flex size-9 items-center justify-center rounded-xl text-white shadow-[0_8px_24px_-8px_var(--primary)]",
        className,
      )}
    >
      <svg viewBox="0 0 32 32" className="size-5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
        <circle cx="16" cy="16" r="7" />
        <circle cx="16" cy="16" r="2" fill="currentColor" stroke="none" />
        <path d="M16 4v3M16 25v3M4 16h3M25 16h3" />
      </svg>
    </span>
  );
}

export function Logo({ className, orgName }: { className?: string; orgName?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <div className="leading-tight">
        <div className="text-[15px] font-semibold tracking-tight">{BRAND.name}</div>
        {orgName && <div className="max-w-40 truncate text-[11px] text-muted-foreground">{orgName}</div>}
      </div>
    </div>
  );
}
