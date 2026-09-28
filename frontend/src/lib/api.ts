import type { components } from "./schema";

type S = components["schemas"];

export type Me = S["Me"];
export type AuthStatus = S["AuthStatus"];
export type Vault = S["VaultOut"];
export type Member = S["MemberOut"];
export type EntryMeta = S["EntryMeta"];
export type EntryFull = S["EntryFull"];
export type EntryInput = S["EntryIn"];
export type SearchHit = S["SearchHit"];
export type Strength = S["StrengthOut"];
export type UrlWarning = S["UrlWarning"];
export type IntelReport = S["IntelReport"];
export type IntelEntry = S["IntelEntry"];
export type IntelFamily = S["IntelFamily"];
export type IntelAction = S["IntelAction"];
export type IntelRef = S["EntryRef"];
export type AdvisorAnswer = S["AdvisorOut"];
export type SiteCheck = S["SiteCheckOut"];
export type TimelineEvent = S["TimelineEvent"];
export type Finding = S["Finding"];
export type Insights = S["Insights"];
export type UserRow = S["UserOut"];
export type DirectoryUser = S["DirectoryUser"];
export type Invite = S["InviteOut"];
export type Policy = S["Policy"];
export type PolicyInput = S["PolicyIn"];
export type MailStatus = S["MailStatus"];
export type MailEvent = S["MailEvent"];
export type OverviewVault = S["OverviewVault"];
export type AuditRow = S["AuditRow"];
export type AuditVerify = S["AuditVerify"];
export type MfaBegin = S["MfaBegin"];

export type OrgRole = "owner" | "admin" | "member" | "auditor";
export type VaultRole = "manager" | "editor" | "viewer";

export class ApiError extends Error {
  status: number;
  code: string;
  retryAfter?: number;
  constructor(status: number, code: string, message: string, retryAfter?: number) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

type Json = Record<string, unknown> | unknown[];

async function request<T>(method: string, path: string, body?: Json): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: {
        // Required by the server on every state-changing call (CSRF defence in depth).
        "X-Requested-With": "kavach",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the server. Check that Kavach is running.");
  }
  if (!res.ok) {
    let code = "error";
    let message = `Request failed (${res.status})`;
    let retryAfter: number | undefined;
    try {
      const data = (await res.json()) as { error?: { code: string; message: string; retry_after?: number } };
      if (data.error) {
        code = data.error.code;
        message = data.error.message;
        retryAfter = data.error.retry_after;
      }
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, code, message, retryAfter);
  }
  return (await res.json()) as T;
}

const get = <T>(path: string) => request<T>("GET", path);
const post = <T>(path: string, body: Json = {}) => request<T>("POST", path, body);
const put = <T>(path: string, body: Json) => request<T>("PUT", path, body);
const patch = <T>(path: string, body: Json) => request<T>("PATCH", path, body);
const del = <T>(path: string) => request<T>("DELETE", path);

const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // auth
  status: () => get<AuthStatus>("/auth/status"),
  setup: (b: { org_name: string; username: string; display_name: string; email: string; password: string }) =>
    post<Me>("/auth/setup", b),
  login: (b: { username: string; password: string; totp_code?: string }) => post<Me>("/auth/login", b),
  activate: (b: { username: string; invite_code: string; password: string }) => post<{ ok: boolean }>("/auth/activate", b),
  setEmail: (email: string, password: string) => put<Me>("/me/email", { email, password }),
  logout: () => post<{ ok: boolean }>("/auth/logout"),
  ping: (idle_seconds: number) => post<{ ok: boolean }>("/auth/ping", { idle_seconds }),
  changePassword: (old_password: string, new_password: string) =>
    post<{ ok: boolean }>("/auth/change-password", { old_password, new_password }),
  me: () => get<Me>("/me"),

  // two-factor
  mfaBegin: () => post<MfaBegin>("/mfa/begin"),
  mfaConfirm: (code: string) => post<{ ok: boolean }>("/mfa/confirm", { code }),
  mfaDisable: (password: string, code: string) => post<{ ok: boolean }>("/mfa/disable", { password, code }),

  // vaults
  vaults: () => get<Vault[]>("/vaults"),
  createVault: (name: string, description = "") => post<{ id: string }>("/vaults", { name, description }),
  updateVault: (id: string, name: string, description = "") => patch<{ ok: boolean }>(`/vaults/${id}`, { name, description }),
  deleteVault: (id: string) => del<{ ok: boolean }>(`/vaults/${id}`),
  members: (id: string) => get<Member[]>(`/vaults/${id}/members`),
  addMember: (id: string, user_id: string, role: VaultRole) => post<{ ok: boolean }>(`/vaults/${id}/members`, { user_id, role }),
  setMemberRole: (id: string, user_id: string, role: VaultRole) =>
    patch<{ ok: boolean }>(`/vaults/${id}/members/${user_id}`, { role }),
  removeMember: (id: string, user_id: string) => del<{ ok: boolean }>(`/vaults/${id}/members/${user_id}`),
  directory: () => get<DirectoryUser[]>("/directory"),

  // entries
  entries: (vaultId: string, q = "") => get<EntryMeta[]>(`/vaults/${vaultId}/entries${qs({ q })}`),
  entry: (vaultId: string, id: string) => get<EntryFull>(`/vaults/${vaultId}/entries/${id}`),
  entryPassword: (vaultId: string, id: string, purpose: "copy" | "view") =>
    get<{ password: string }>(`/vaults/${vaultId}/entries/${id}/password${qs({ purpose })}`),
  addEntry: (vaultId: string, e: EntryInput) => post<{ id: string }>(`/vaults/${vaultId}/entries`, e),
  updateEntry: (vaultId: string, id: string, e: EntryInput) => put<{ ok: boolean }>(`/vaults/${vaultId}/entries/${id}`, e),
  deleteEntries: (vaultId: string, ids: string[]) => post<{ deleted: number }>(`/vaults/${vaultId}/entries/delete`, { ids }),
  revealAll: (vaultId: string) => post<{ passwords: Record<string, string> }>(`/vaults/${vaultId}/reveal-all`),
  search: (q: string, limit = 12) => get<SearchHit[]>(`/search${qs({ q, limit })}`),

  // tools
  strength: (password: string, inputs: string[] = []) => post<Strength>("/auth/strength", { password, inputs }),
  urlCheck: (url: string) => post<UrlWarning[]>("/tools/url-check", { url }),
  generate: (o: { length: number; digits: boolean; symbols: boolean; ambiguous: boolean }) =>
    post<{ password: string }>("/tools/generate", o),

  // security intelligence
  intel: (breach = false, quiet = false) => get<IntelReport>(`/intel${qs({ breach, quiet })}`),
  advisor: (question: string) => post<AdvisorAnswer>("/intel/advisor", { question }),
  timeline: () => get<TimelineEvent[]>("/intel/timeline"),
  siteCheck: (url: string) => post<SiteCheck>("/tools/site-check", { url }),

  // audit insights
  insights: (days = 7) => get<Insights>(`/insights${qs({ days })}`),

  // admin
  users: () => get<UserRow[]>("/users"),
  invite: (b: { username: string; display_name: string; email: string; role: OrgRole; send_email?: boolean }) => post<Invite>("/users", b),
  setRole: (id: string, role: OrgRole) => patch<{ ok: boolean }>(`/users/${id}/role`, { role }),
  disableUser: (id: string) => post<{ ok: boolean }>(`/users/${id}/disable`),
  enableUser: (id: string) => post<{ ok: boolean }>(`/users/${id}/enable`),
  resetAccess: (id: string) => post<Invite>(`/users/${id}/reset-access`),
  reissueInvite: (id: string) => post<Invite>(`/users/${id}/reissue-invite`),
  resetMfa: (id: string) => post<{ ok: boolean }>(`/users/${id}/reset-mfa`),
  policy: () => get<Policy>("/policy"),
  setPolicy: (p: PolicyInput) => put<Policy>("/policy", p),
  overview: () => get<OverviewVault[]>("/vaults-overview"),
  mail: () => get<MailStatus>("/mail"),
  testMail: () => post<{ ok: boolean }>("/mail/test"),

  // audit
  audit: (prefix: string, actor: string, limit = 300) => get<AuditRow[]>(`/audit${qs({ prefix, actor, limit })}`),
  verifyAudit: () => get<AuditVerify>("/audit/verify"),
};
