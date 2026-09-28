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


class EntryMeta(Model):
    id: str
    service: str
    username: str
    url: str
    notes: str
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


# ── health / insights ────────────────────────────────────────────────────
class EntryRef(Model):
    id: str
    vault_id: str
    vault: str
    service: str
    username: str


class Issue(Model):
    kind: str
    detail: str


class HealthEntry(Model):
    ref: EntryRef
    health: int
    issues: List[Issue]


class HealthReport(Model):
    score: int
    label: str
    color: str
    total: int
    counts: dict
    entries: List[HealthEntry]
    breach_checked: bool
    note: Optional[str] = None
    breach_allowed: bool = False


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


class InviteOut(Model):
    user_id: Optional[str] = None
    username: str
    invite_code: str
    valid_hours: int


class Policy(Model):
    min_password_length: int
    idle_timeout_secs: int
    max_attempts: int
    lockout_secs: int
    invite_ttl_hours: int
    breach_check: int


class PolicyIn(Strict):
    min_password_length: Optional[int] = None
    idle_timeout_secs: Optional[int] = None
    max_attempts: Optional[int] = None
    lockout_secs: Optional[int] = None
    invite_ttl_hours: Optional[int] = None
    breach_check: Optional[int] = None


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
