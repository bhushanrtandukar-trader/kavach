"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Copy, HeartPulse, KeyRound, Lock, LogOut, Moon, Plus, ScrollText, Search, Settings2, Sun, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Kbd, Avatar } from "@/components/ui/misc";
import { useVault } from "@/components/vault-context";
import { api, type Me } from "@/lib/api";
import { emit, setPendingOpen } from "@/lib/events";
import { canAdmin, canAudit, canCreateVault, useDebounced } from "@/lib/hooks";
import { copySecret, serviceLetters, serviceStyle } from "@/lib/utils";

const item =
  "flex cursor-pointer select-none items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-foreground/90 outline-none data-[selected=true]:bg-primary/12 data-[selected=true]:text-foreground [&_svg]:size-4 [&_svg]:text-muted-foreground data-[selected=true]:[&_svg]:text-primary";

/** ⌘K / Ctrl+K: jump anywhere, act, or find an entry (typo-tolerant) without leaving the keyboard. */
export function CommandPalette({ me }: { me: Me }) {
  const router = useRouter();
  const { setTheme, resolvedTheme } = useTheme();
  const { vaults, select } = useVault();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const debounced = useDebounced(q, 150);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    const h = () => setOpen(true);
    window.addEventListener("kv:open-palette", h);
    return () => window.removeEventListener("kv:open-palette", h);
  }, []);

  const hits = useQuery({
    queryKey: ["palette", debounced],
    queryFn: () => api.search(debounced, 8),
    enabled: open && debounced.trim().length > 0,
    placeholderData: (p) => p,
  });

  const go = (fn: () => void) => {
    setOpen(false);
    setQ("");
    setTimeout(fn, 40);
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={(o) => (setOpen(o), !o && setQ(""))}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="anim-overlay fixed inset-0 z-50 bg-black/55 backdrop-blur-sm" />
        <DialogPrimitive.Content
          aria-label="Command palette"
          className="anim-dialog glass-solid fixed left-1/2 top-[18%] z-50 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-3xl p-0 outline-none"
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">Search entries and run commands</DialogPrimitive.Description>
          <Command loop className="flex max-h-[62dvh] flex-col">
            <div className="flex items-center gap-3 border-b px-4">
              <Search className="size-4 text-muted-foreground" />
              <Command.Input
                value={q}
                onValueChange={setQ}
                placeholder="Search entries, jump to a page, run a command…"
                className="h-14 flex-1 bg-transparent text-[15px] outline-none focus-visible:outline-none placeholder:text-muted-foreground/70"
              />
              <Kbd>esc</Kbd>
            </div>
            <Command.List className="overflow-y-auto p-2">
              <Command.Empty className="px-4 py-10 text-center text-sm text-muted-foreground">Nothing matches “{q}”.</Command.Empty>

              {debounced.trim() && (hits.data?.length ?? 0) > 0 && (
                <Command.Group heading="Entries" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground">
                  {hits.data?.map((h) => (
                    <Command.Item
                      key={h.vault_id + h.id}
                      forceMount
                      value={`entry-${h.vault_id}-${h.id}`}
                      className={item}
                      onSelect={() =>
                        go(() => {
                          select(h.vault_id);
                          setPendingOpen({ vaultId: h.vault_id, entryId: h.id });
                          router.push("/vaults");
                          emit("kv:open-entry", { vaultId: h.vault_id, entryId: h.id });
                        })
                      }
                    >
                      <Avatar name={h.service} gradient={serviceStyle(h.service).background} className="!size-8 !rounded-lg !text-[11px]">
                        {serviceLetters(h.service)}
                      </Avatar>
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{h.service}</div>
                        <div className="truncate text-xs text-muted-foreground">
                          {h.username || "—"} · {h.vault}
                        </div>
                      </div>
                      <button
                        className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                        aria-label="Copy password"
                        onPointerDown={(e) => e.stopPropagation()}
                        onClick={async (e) => {
                          e.stopPropagation();
                          try {
                            const { password } = await api.entryPassword(h.vault_id, h.id, "copy");
                            await copySecret(password);
                            toast.success(`Password for ${h.service} copied`, { description: "The clipboard clears in 30 seconds." });
                            setOpen(false);
                          } catch {
                            toast.error("Could not copy that password");
                          }
                        }}
                      >
                        <Copy className="size-4" />
                      </button>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}

              <Command.Group heading="Go to" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground">
                <Command.Item className={item} onSelect={() => go(() => router.push("/vaults"))}>
                  <KeyRound /> Vaults
                </Command.Item>
                <Command.Item className={item} onSelect={() => go(() => router.push("/health"))}>
                  <HeartPulse /> Vault health
                </Command.Item>
                {canAdmin(me.role) && (
                  <Command.Item className={item} onSelect={() => go(() => router.push("/admin"))}>
                    <Users /> People &amp; policy
                  </Command.Item>
                )}
                {canAudit(me.role) && (
                  <Command.Item className={item} onSelect={() => go(() => router.push("/audit"))}>
                    <ScrollText /> Audit &amp; insights
                  </Command.Item>
                )}
                <Command.Item className={item} onSelect={() => go(() => router.push("/account"))}>
                  <Settings2 /> Account &amp; two-factor
                </Command.Item>
              </Command.Group>

              {vaults.length > 0 && (
                <Command.Group heading="Switch vault" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground">
                  {vaults.map((v) => (
                    <Command.Item
                      key={v.id}
                      value={`vault ${v.kind === "personal" ? "personal" : v.name}`}
                      className={item}
                      onSelect={() =>
                        go(() => {
                          select(v.id);
                          router.push("/vaults");
                        })
                      }
                    >
                      <Lock /> {v.kind === "personal" ? "Personal" : v.name}
                      <span className="ml-auto text-xs text-muted-foreground">{v.entry_count} entries</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}

              <Command.Group heading="Actions" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground">
                <Command.Item
                  className={item}
                  onSelect={() =>
                    go(() => {
                      router.push("/vaults");
                      setTimeout(() => emit("kv:new-entry"), 80);
                    })
                  }
                >
                  <Plus /> New entry
                </Command.Item>
                {canCreateVault(me.role) && (
                  <Command.Item
                    className={item}
                    onSelect={() =>
                      go(() => {
                        router.push("/vaults");
                        setTimeout(() => emit("kv:new-vault"), 80);
                      })
                    }
                  >
                    <Plus /> New shared vault
                  </Command.Item>
                )}
                <Command.Item className={item} onSelect={() => go(() => setTheme(resolvedTheme === "dark" ? "light" : "dark"))}>
                  {resolvedTheme === "dark" ? <Sun /> : <Moon />} Switch to {resolvedTheme === "dark" ? "light" : "dark"} mode
                </Command.Item>
                <Command.Item
                  className={item}
                  onSelect={() =>
                    go(async () => {
                      try {
                        await api.logout();
                      } finally {
                        window.location.assign("/login");
                      }
                    })
                  }
                >
                  <LogOut /> Lock &amp; sign out
                </Command.Item>
              </Command.Group>
            </Command.List>
            <div className="flex items-center justify-between border-t px-4 py-2.5 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-3">
                <span><Kbd>↑</Kbd> <Kbd>↓</Kbd> navigate</span>
                <span><Kbd>↵</Kbd> select</span>
              </span>
              <span>Typo-tolerant search</span>
            </div>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
