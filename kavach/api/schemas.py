"""Request and response models.  These also produce the OpenAPI schema the frontend's types are generated from."""
from typing import List, Optional

from pydantic import BaseModel, Field


class Model(BaseModel):
    """Responses: fields not declared here are dropped, so database columns never leak by accident."""
    model_config = {'extra': 'ignore'}


class Strict(BaseModel):
    """Requests: unknown fields are refused."""
    model_config = {'extra': 'forbid'}


# ── auth ─────────────────────────────────────────────────────────────────
class SetupIn(Strict):
    org_name: str = Field(max_length=100)
    username: str = Field(max_length=64)
    display_name: str = Field('', max_length=80)
    email: str = Field('', max_length=320)
    password: str = Field(max_length=256)


class LoginIn(Strict):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    totp_code: Optional[str] = Field(None, max_length=16)


class ActivateIn(Strict):
    username: str = Field(max_length=64)
    invite_code: str = Field(max_length=128)
    password: str = Field(max_length=256)


class ChangePasswordIn(Strict):
    old_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class PingIn(Strict):
    idle_seconds: float = Field(0, ge=0)


class Me(Model):
    id: str
    username: str
    display_name: str
    email: str
    role: str
    totp_enabled: bool
    last_login: Optional[float] = None
    org_name: str


class ExtSession(Model):
    me: Me
    idle_timeout_secs: int


class ExtLoginOut(ExtSession):
    token: str


class AuthStatus(Model):
    initialized: bool
    org_name: str
    me: Optional[Me] = None
    idle_timeout_secs: int = 900


class Ok(Model):
    ok: bool = True


# ── vaults / entries ─────────────────────────────────────────────────────
class VaultOut(Model):
    id: str
    name: str
    description: str
    kind: str
    role: str
    entry_count: int
    member_count: int


class VaultIn(Strict):
    name: str = Field(max_length=100)
    description: str = Field('', max_length=500)


class VaultCreated(Model):
    id: str


class MemberOut(Model):
    user_id: str
    username: str
    display_name: str
    role: str
    status: str
    added_at: float


class MemberIn(Strict):
    user_id: str
    role: str


class RoleIn(Strict):
    role: str


class EntryIn(Strict):
    service: str = Field(max_length=200)
    username: str = Field('', max_length=200)
    password: str = Field(max_length=1000)
    url: str = Field('', max_length=500)
    notes: str = Field('', max_length=5000)
    mfa: bool = False


class EntryMeta(Model):
    id: str
    service: str
    username: str
    url: str
    notes: str
    mfa: bool = False
    updated_at: float
    created_at: float
    password_changed_at: Optional[float] = None
    corrupt: bool = False


class EntryFull(Model):
    id: str
    service: str
    username: str
    password: str
    url: str
    notes: str
    mfa: bool = False


class EntryCreated(Model):
    id: str


class IdsIn(Strict):
    ids: List[str] = Field(max_length=1000)


class Deleted(Model):
    deleted: int


class PasswordOut(Model):
    password: str


class RevealAll(Model):
    passwords: dict


class SearchHit(EntryMeta):
    vault_id: str
    vault: str


# ── tools ────────────────────────────────────────────────────────────────
class StrengthIn(Strict):
    password: str = Field(max_length=256)
    inputs: List[str] = Field(default_factory=list, max_length=10)


class StrengthOut(Model):
    score: int
    percent: int
    label: str
    crack_time: str
    warning: str
    suggestions: List[str]


class UrlCheckIn(Strict):
    url: str = Field(max_length=500)


class PageIn(Strict):
    url: str = Field(max_length=2000)


class ExtCredentialIn(Strict):
    url: str = Field(max_length=2000)
    vault_id: str = Field(max_length=64)
    entry_id: str = Field(max_length=64)
    confirmed: bool = False


class ExtCredential(Model):
    service: str
    username: str
    password: str


class ExtAction(Model):
    title: str
    priority: str


class ExtSummary(Model):
    score: int
    label: str
    total: int
    actions: List[ExtAction]


class UrlWarning(Model):
    level: str
    message: str


class GenerateIn(Strict):
    length: int = Field(20, ge=8, le=128)
    digits: bool = True
    symbols: bool = True
    ambiguous: bool = False


class Generated(Model):
    password: str


# ── security intelligence ────────────────────────────────────────────────
class EntryRef(Model):
    id: str
    vault_id: str
    vault: str
    service: str
    username: str


class IntelFactor(Model):
    code: str
    label: str
    p: float
    detail: str


class IntelEntry(Model):
    ref: EntryRef
    category: str
    category_label: str
    importance: str
    risk: int
    level: str
    priority: str
    priority_score: float
    factors: List[IntelFactor]
    headline: str
    advice: str
    reuse_count: int
    family: Optional[str] = None
    age_days: int
    exposure: str
    mfa: bool
    strength: int


class IntelFamily(Model):
    id: str
    kind: str
    size: int
    distinct: int
    suffix_only: bool
    members: List[EntryRef]
    summary: str


class IntelAction(Model):
    kind: str
    ref: EntryRef
    gain: float
    title: str
    why: str
    priority: str


class IntelSummary(Model):
    accounts: int
    strong: int
    reused: int
    weak: int
    families: int
    breached: int
    old: int
    critical_accounts: int
    critical_without_mfa: int
    mfa_enabled: int


class IntelReport(Model):
    score: int
    label: str
    color: str
    total: int
    summary: IntelSummary
    entries: List[IntelEntry]
    families: List[IntelFamily]
    actions: List[IntelAction]
    breach_checked: bool
    breach_allowed: bool = False
    note: Optional[str] = None
    generated_at: float


class AdvisorIn(Strict):
    question: str = Field(max_length=300)


class AdvisorOut(Model):
    intent: str
    answer: str
    bullets: List[str]
    refs: List[EntryRef]
    suggestions: List[str]


class SiteSignal(Model):
    code: str
    weight: int
    message: str


class SiteCheckOut(Model):
    url: str
    domain: str
    risk: int
    level: str
    decision: str
    reasons: List[str]
    signals: List[SiteSignal]
    matches: List[EntryRef]
    impersonates: List[EntryRef]


class TimelineEvent(Model):
    ts: float
    kind: str
    title: str
    detail: str


# ── audit insights ───────────────────────────────────────────────────────
class Finding(Model):
    severity: str
    kind: str
    who: str
    ts: float
    title: str
    detail: str
    advice: str


class Insights(Model):
    findings: List[Finding]
    events_analysed: int
    days: int


# ── admin ────────────────────────────────────────────────────────────────
class UserOut(Model):
    id: str
    username: str
    display_name: str
    email: str
    role: str
    status: str
    last_login: Optional[float] = None
    created_at: float
    totp_enabled: bool


class DirectoryUser(Model):
    id: str
    username: str
    display_name: str
    role: str


class InviteIn(Strict):
    username: str = Field(max_length=64)
    display_name: str = Field('', max_length=80)
    email: str = Field('', max_length=320)
    role: str
    send_email: bool = True


class InviteOut(Model):
    user_id: Optional[str] = None
    username: str
    invite_code: str
    valid_hours: int
    emailed: bool = False                  # whether the code was also sent to the person's email address


class Policy(Model):
    min_password_length: int
    idle_timeout_secs: int
    max_attempts: int
    lockout_secs: int
    invite_ttl_hours: int
    breach_check: int
    email_alerts: int
    email_digest: int


class PolicyIn(Strict):
    min_password_length: Optional[int] = None
    idle_timeout_secs: Optional[int] = None
    max_attempts: Optional[int] = None
    lockout_secs: Optional[int] = None
    invite_ttl_hours: Optional[int] = None
    breach_check: Optional[int] = None
    email_alerts: Optional[int] = None
    email_digest: Optional[int] = None


class EmailIn(Strict):
    email: str = Field('', max_length=320)
    password: str = Field(max_length=256)


class MailEvent(Model):
    ts: float
    ok: bool
    kind: str
    to: str
    error: str = ''


class MailStatus(Model):
    configured: bool
    host: str
    port: int
    security: str
    sender: str
    public_url: str
    recent: List[MailEvent]


class OverviewVault(Model):
    id: str
    name: str
    kind: str
    created_at: float
    needs_rotation: int
    created_by: str
    entry_count: int
    member_count: int


class AuditRow(Model):
    id: int
    ts: float
    actor_id: Optional[str] = None
    actor_name: str
    action: str
    target: str
    detail: str
    ip: str


class AuditVerify(Model):
    ok: bool
    first_bad_id: Optional[int] = None
    checked: int


# ── two-factor ───────────────────────────────────────────────────────────
class MfaBegin(Model):
    secret: str
    uri: str
    qr: str


class MfaConfirmIn(Strict):
    code: str = Field(max_length=16)


class MfaDisableIn(Strict):
    password: str = Field(max_length=256)
    code: str = Field(max_length=16)
