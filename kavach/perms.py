"""Who may do what.  Pure functions, easy to test.

Organisation roles (what you can do to the *organisation*):

    owner    everything, including appointing admins and other owners
    admin    manage members/auditors, policies, the audit log, delete vaults
    member   normal user: personal vault, create/join shared vaults
    auditor  read-only access to the audit log; no vault creation

Vault roles (what you can do inside one *shared vault*):

    manager  everything in the vault, including who has access
    editor   add / edit / delete entries
    viewer   read and copy entries

Being an admin does NOT grant access to a vault's contents.  Vault keys are
wrapped per member, so an admin who is not a member cannot decrypt anything.
"""

ORG_ROLES = ('owner', 'admin', 'member', 'auditor')
VAULT_ROLES = ('manager', 'editor', 'viewer')

_VAULT_ACTIONS = {
    'manager': {'read', 'write', 'share', 'delete'},
    'editor': {'read', 'write'},
    'viewer': {'read'},
}


def assignable_roles(actor_role: str) -> tuple:
    """Roles the actor may give to a user."""
    if actor_role == 'owner':
        return ORG_ROLES
    if actor_role == 'admin':
        return ('member', 'auditor')
    return ()


def can_modify_user(actor_role: str, target_role: str) -> bool:
    if actor_role == 'owner':
        return True
    if actor_role == 'admin':
        return target_role in ('member', 'auditor')
    return False


def can_manage_users(role: str) -> bool:
    return role in ('owner', 'admin')


def can_manage_policy(role: str) -> bool:
    return role in ('owner', 'admin')


def can_view_audit(role: str) -> bool:
    return role in ('owner', 'admin', 'auditor')


def can_list_users(role: str) -> bool:
    return role in ('owner', 'admin', 'auditor')


def can_create_vault(role: str) -> bool:
    return role in ('owner', 'admin', 'member')


def can_delete_any_vault(role: str) -> bool:
    return role in ('owner', 'admin')


def vault_can(vault_role: str, action: str) -> bool:
    return action in _VAULT_ACTIONS.get(vault_role, ())
