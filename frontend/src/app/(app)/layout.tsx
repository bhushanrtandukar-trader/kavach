"use client";

import { Menu, Search } from "lucide-react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { motion } from "motion/react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CommandPalette } from "@/components/command-palette";
import { IdleGuard } from "@/components/idle-guard";
import { SidebarBody, navItems } from "@/components/sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/misc";
import { VaultProvider } from "@/components/vault-context";
import { useStatus } from "@/lib/hooks";

function Splash() {
  return (
    <div className="flex min-h-dvh items-center justify-center">
      <div className="gradient-bg size-12 animate-pulse rounded-2xl" />
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const status = useStatus();
  const [drawer, setDrawer] = useState(false);
  const me = status.data?.me;

  // The gate: no session, no app. (The server enforces this too; this just moves you to the right screen.)
  useEffect(() => {
    if (status.isSuccess && (!status.data.initialized || !status.data.me)) router.replace("/login");
  }, [status.isSuccess, status.data, router]);

  useEffect(() => setDrawer(false), [pathname]);

  if (!me || !status.data) return <Splash />;
  const title = navItems(me).find((n) => pathname === n.href || pathname === n.href + "/")?.label ?? "Kavach";

  return (
    <VaultProvider>
      <div className="mx-auto flex min-h-dvh max-w-[1600px]">
        {/* desktop sidebar */}
        <aside className="glass sticky top-0 m-3 mr-0 hidden h-[calc(100dvh-1.5rem)] w-72 shrink-0 overflow-hidden rounded-3xl lg:block">
          <SidebarBody me={me} orgName={status.data.org_name} />
        </aside>

        {/* mobile drawer */}
        <DialogPrimitive.Root open={drawer} onOpenChange={setDrawer}>
          <DialogPrimitive.Portal>
            <DialogPrimitive.Overlay className="anim-overlay fixed inset-0 z-40 bg-black/55 backdrop-blur-sm lg:hidden" />
            <DialogPrimitive.Content className="anim-sheet-left glass-solid fixed inset-y-0 left-0 z-50 w-80 max-w-[85vw] overflow-hidden rounded-r-3xl outline-none lg:hidden">
              <DialogPrimitive.Title className="sr-only">Navigation</DialogPrimitive.Title>
              <DialogPrimitive.Description className="sr-only">Pages and vaults</DialogPrimitive.Description>
              <SidebarBody me={me} orgName={status.data.org_name} onNavigate={() => setDrawer(false)} />
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex items-center gap-3 px-4 py-3 sm:px-6">
            <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" onClick={() => setDrawer(true)}>
              <Menu />
            </Button>
            <h1 className="text-lg font-semibold tracking-tight lg:hidden">{title}</h1>
            <button
              onClick={() => window.dispatchEvent(new Event("kv:open-palette"))}
              className="glass ml-auto flex h-10 w-full max-w-sm items-center gap-2.5 rounded-xl px-3.5 text-sm text-muted-foreground transition hover:text-foreground lg:ml-0"
            >
              <Search className="size-4" />
              <span className="flex-1 text-left">Search or jump to…</span>
              <Kbd>Ctrl</Kbd>
              <Kbd>K</Kbd>
            </button>
            <div className="ml-auto hidden lg:block">
              <ThemeToggle />
            </div>
          </header>

          <motion.main
            key={pathname}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="flex-1 px-4 pb-16 pt-2 sm:px-6"
          >
            {children}
          </motion.main>
        </div>
      </div>
      <CommandPalette me={me} />
      <IdleGuard timeoutSecs={status.data.idle_timeout_secs} />
    </VaultProvider>
  );
}
