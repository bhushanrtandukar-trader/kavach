"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { type Vault } from "@/lib/api";
import { useVaults } from "@/lib/hooks";

interface Ctx {
  vaults: Vault[];
  loading: boolean;
  vaultId: string | null;
  vault: Vault | undefined;
  select: (id: string) => void;
}

const VaultCtx = createContext<Ctx | null>(null);
const KEY = "kv:vault";

/** Which vault is open. Only an id is remembered (per tab): it is not a secret. */
export function VaultProvider({ children }: { children: ReactNode }) {
  const { data, isLoading } = useVaults();
  const vaults = useMemo(() => data ?? [], [data]);
  const [chosen, setChosen] = useState<string | null>(null);

  useEffect(() => {
    try {
      setChosen(sessionStorage.getItem(KEY));
    } catch {
      /* storage blocked: fine */
    }
  }, []);

  const vaultId = useMemo(() => {
    if (vaults.length === 0) return null;
    if (chosen && vaults.some((v) => v.id === chosen)) return chosen;
    return (vaults.find((v) => v.kind === "personal") ?? vaults[0])?.id ?? null;
  }, [vaults, chosen]);

  const select = useCallback((id: string) => {
    setChosen(id);
    try {
      sessionStorage.setItem(KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<Ctx>(
    () => ({ vaults, loading: isLoading, vaultId, vault: vaults.find((v) => v.id === vaultId), select }),
    [vaults, isLoading, vaultId, select],
  );
  return <VaultCtx.Provider value={value}>{children}</VaultCtx.Provider>;
}

export function useVault(): Ctx {
  const c = useContext(VaultCtx);
  if (!c) throw new Error("useVault must be used inside <VaultProvider>");
  return c;
}
