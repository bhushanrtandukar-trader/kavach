/** A tiny typed event bus so distant components (command palette, health page) can ask the vault page to act. */
export interface GkEvents {
  "kv:new-entry": undefined;
  "kv:open-entry": { vaultId: string; entryId: string };
  "kv:new-vault": undefined;
  "kv:focus-search": undefined;
}

export function emit<K extends keyof GkEvents>(name: K, detail?: GkEvents[K]) {
  window.dispatchEvent(new CustomEvent(name, { detail }));
}

export function on<K extends keyof GkEvents>(name: K, fn: (detail: GkEvents[K]) => void): () => void {
  const h = (e: Event) => fn((e as CustomEvent<GkEvents[K]>).detail);
  window.addEventListener(name, h);
  return () => window.removeEventListener(name, h);
}

/** Survives a page navigation (used by "Fix" buttons that jump to an entry). */
const PENDING = "kv:pending-open";
export function setPendingOpen(v: GkEvents["kv:open-entry"]) {
  try {
    sessionStorage.setItem(PENDING, JSON.stringify(v));
  } catch {
    /* ignore */
  }
}
export function takePendingOpen(): GkEvents["kv:open-entry"] | null {
  try {
    const raw = sessionStorage.getItem(PENDING);
    if (!raw) return null;
    sessionStorage.removeItem(PENDING);
    return JSON.parse(raw) as GkEvents["kv:open-entry"];
  } catch {
    return null;
  }
}
