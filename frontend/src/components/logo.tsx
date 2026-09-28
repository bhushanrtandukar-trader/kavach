import { BRAND } from "@/lib/brand";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src="/icon.png" alt="" width={36} height={36} className={cn("size-9 shrink-0 drop-shadow-[0_6px_16px_-6px_var(--primary)]", className)} />
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
