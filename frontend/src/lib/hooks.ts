"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type OrgRole } from "@/lib/api";

export function useStatus() {
  return useQuery({ queryKey: ["status"], queryFn: api.status, staleTime: 5_000 });
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useVaults() {
  return useQuery({ queryKey: ["vaults"], queryFn: api.vaults });
}

export const canAdmin = (role?: OrgRole | string) => role === "owner" || role === "admin";
export const canAudit = (role?: OrgRole | string) => role === "owner" || role === "admin" || role === "auditor";
export const canCreateVault = (role?: OrgRole | string) => role === "owner" || role === "admin" || role === "member";

/** Is the page a small screen? (used to pick drawer vs sidebar) */
export function useMediaQuery(query: string): boolean {
  const [match, setMatch] = useState(false);
  useEffect(() => {
    const m = window.matchMedia(query);
    setMatch(m.matches);
    const on = () => setMatch(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return match;
}
