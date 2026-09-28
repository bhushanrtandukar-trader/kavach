"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Activity, HeartPulse, KeyRound, Lock, LogOut, Plus, ScrollText, Settings2, ShieldCheck, Users } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { Avatar, RoleBadge } from "@/components/ui/misc";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/menu";
import { useVault } from "@/components/vault-context";
import { api, type Me } from "@/lib/api";
import { emit } from "@/lib/events";
import { canAdmin, canAudit, canCreateVault } from "@/lib/hooks";
import { cn, gradientFor, initials } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  show: boolean;
}

export function navItems(me: Me): NavItem[] {
  return [
    { href: "/vaults", label: "Vaults", icon: KeyRound, show: true },
    { href: "/health", label: "Health", icon: HeartPulse, show: true },
    { href: "/admin", label: "People & policy", icon: Users, show: canAdmin(me.role) },
    { href: "/audit", label: "Audit & insights", icon: ScrollText, show: canAudit(me.role) },
    { href: "/account", label: "Account", icon: Settings2, show: true },
  ].filter((i) => i.show);
}

export function UserMenu({ me }: { me: Me }) {
  const qc = useQueryClient();
  const router = useRouter();
  async function signOut() {
    try {
      await api.logout();
    } finally {
      qc.clear();
      window.location.assign("/login");
    }
    router.replace("/login");
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex w-full items-center gap-3 rounded-2xl p-2 text-left outline-none transition hover:bg-muted focus-visible:bg-muted">
          <Avatar name={me.display_name} gradient={gradientFor(me.username)} className="size-10 rounded-xl">
            {initials(me.display_name)}
          </Avatar>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate text-sm font-medium">{me.display_name}</div>
            <div className="truncate text-xs text-muted-foreground">@{me.username}</div>
          </div>
          <RoleBadge role={me.role} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-60">
        <DropdownMenuLabel>{me.email || `@${me.username}`}</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => router.push("/account")}>
          <Settings2 /> Account settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem danger onSelect={() => void signOut()}>
          <LogOut /> Lock &amp; sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Shared by the desktop sidebar and the mobile drawer. */
export function SidebarBody({ me, orgName, onNavigate }: { me: Me; orgName: string; onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { vaults, vaultId, select, loading } = useVault();
  const personal = vaults.filter((v) => v.kind === "personal");
  const shared = vaults.filter((v) => v.kind === "shared");

  function openVault(id: string) {
    select(id);
    router.push("/vaults");
    onNavigate?.();
  }

  return (
    <div className="flex h-full flex-col gap-5 p-4">
      <div className="flex items-center justify-between px-1.5 pt-1">
        <Logo orgName={orgName} />
        <ThemeToggle />
      </div>

      <nav className="space-y-1" aria-label="Main">
        {navItems(me).map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname === href + "/";
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className={cn(
                "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                active ? "text-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
              )}
            >
              {active && (
                <motion.span layoutId="nav-active" className="absolute inset-0 rounded-xl bg-primary/12 ring-1 ring-primary/25" transition={{ type: "spring", stiffness: 420, damping: 34 }} />
              )}
              <Icon className={cn("relative size-[18px]", active && "text-primary")} />
              <span className="relative">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
        <div className="mb-2 flex items-center justify-between px-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Vaults</span>
          {canCreateVault(me.role) && (
            <button
              onClick={() => {
                router.push("/vaults");
                setTimeout(() => emit("kv:new-vault"), 60);
                onNavigate?.();
              }}
              aria-label="New shared vault"
              className="flex size-6 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              <Plus className="size-4" />
            </button>
          )}
        </div>
        <ul className="space-y-0.5">
          {loading && [0, 1, 2].map((i) => <li key={i} className="skeleton mx-1 my-1 h-9" />)}
          {[...personal, ...shared].map((v) => {
            const active = v.id === vaultId && pathname.startsWith("/vaults");
            return (
              <li key={v.id}>
                <button
                  onClick={() => openVault(v.id)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-sm transition-colors",
                    active ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  <span
                    style={{ background: v.kind === "personal" ? "linear-gradient(135deg,#6b46ff,#a855f7)" : gradientFor(v.name) }}
                    className="flex size-6 shrink-0 items-center justify-center rounded-lg text-white"
                  >
                    {v.kind === "personal" ? <Lock className="size-3.5" /> : <span className="text-[10px] font-bold">{initials(v.name).slice(0, 1)}</span>}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{v.kind === "personal" ? "Personal" : v.name}</span>
                  <span className="text-[11px] tabular-nums text-muted-foreground">{v.entry_count}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="space-y-2 border-t pt-3">
        <div className="flex items-center gap-2 px-2 text-[11px] text-muted-foreground">
          <ShieldCheck className="size-3.5 text-success" /> Per-vault encryption
          <Activity className="ml-auto size-3.5" />
        </div>
        <UserMenu me={me} />
      </div>
    </div>
  );
}
