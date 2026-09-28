"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, useTheme } from "next-themes";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";

/** When the server says the session is over, tell the shell so it can lock the screen. */
function handleGlobalError(error: unknown, client: QueryClient) {
  if (error instanceof ApiError && error.code === "session_expired") {
    client.setQueryData(["status"], (old: unknown) =>
      old && typeof old === "object" ? { ...(old as object), me: null } : old,
    );
    client.removeQueries({ predicate: (q) => q.queryKey[0] !== "status" });
  }
}

function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  return (
    <Toaster
      position="bottom-right"
      theme={resolvedTheme === "light" ? "light" : "dark"}
      style={
        {
          "--normal-bg": "var(--card-solid)",
          "--normal-text": "var(--foreground)",
          "--normal-border": "var(--border)",
          "--success-bg": "var(--card-solid)",
          "--success-text": "var(--foreground)",
          "--success-border": "var(--border)",
          "--error-bg": "var(--card-solid)",
          "--error-text": "var(--foreground)",
          "--error-border": "var(--danger)",
        } as React.CSSProperties
      }
      toastOptions={{ classNames: { toast: "!rounded-2xl !shadow-soft", description: "!text-muted-foreground" } }}
    />
  );
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => {
    const c: QueryClient = new QueryClient({
      queryCache: new QueryCache({ onError: (e) => handleGlobalError(e, c) }),
      mutationCache: new MutationCache({ onError: (e) => handleGlobalError(e, c) }),
      defaultOptions: {
        queries: {
          staleTime: 15_000,
          refetchOnWindowFocus: false,
          retry: (count, err) => !(err instanceof ApiError) && count < 2,
        },
      },
    });
    return c;
  });

  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <TooltipProvider delayDuration={200}>
          {children}
          <ThemedToaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
