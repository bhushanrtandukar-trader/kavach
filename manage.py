#!/usr/bin/env python
"""Administration commands that run on the server, outside the web UI.

    python manage.py import-legacy --from <folder> --user <username>
    python manage.py backup <destination-file>
    python manage.py verify-audit
    python manage.py info
"""
import argparse
import getpass
import os
import sqlite3
import sys

from guptakosh import audit, config
from guptakosh.core import Core
from guptakosh.errors import AppError
from guptakosh.legacy import import_entries, read_legacy_vault


def cmd_import_legacy(core, args):
    print(f"Reading the old vault in {args.source} (nothing there is modified).")
    master = getpass.getpass('Old master password: ')
    secondary = getpass.getpass('Old secondary password: ')
    entries = read_legacy_vault(args.source, master, secondary)
    print(f'Found {len(entries)} entries.')
    password = getpass.getpass(f'Guptakosh password for {args.user}: ')
    token = core.accounts.login(args.user, password, 'cli')
    try:
        vaults = core.vaults.list_vaults(token)
        target = next((v for v in vaults if v['kind'] == 'personal'), None) if not args.vault else \
            next((v for v in vaults if v['name'].lower() == args.vault.lower()), None)
        if target is None:
            sys.exit('That vault was not found (or you have no access to it).')
        done, skipped = import_entries(core, token, target['id'], entries)
        print(f"Imported {done} entries into '{target['name']}'.")
        for s in skipped:
            print('  skipped', s)
    finally:
        core.accounts.logout(token)
    print('Done. Once you have checked the result, securely delete the old config.json / passwords.json.')


def cmd_backup(core, args):
    """Consistent online snapshot (safe while the server is running)."""
    if os.path.exists(args.dest):
        sys.exit(f'{args.dest} already exists; refusing to overwrite.')
    src = sqlite3.connect(core.db.path)
    dst = sqlite3.connect(args.dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    try:
        os.chmod(args.dest, 0o600)
    except OSError:
        pass
    print(f'Backup written to {args.dest}. It is encrypted at rest but still sensitive: store it safely.')


def cmd_verify_audit(core, args):
    with core.db.read() as c:
        ok, bad, n = audit.verify(c)
    if ok:
        print(f'Audit log OK: {n} events, unbroken chain.')
    else:
        sys.exit(f'AUDIT LOG TAMPERED: the chain breaks at event #{bad} (of {n} checked).')


def cmd_info(core, args):
    with core.db.read() as c:
        counts = {t: c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                  for t in ('users', 'vaults', 'entries', 'audit')}
    print(f'Data directory: {config.DATA_DIR}')
    print('  ' + ', '.join(f'{k}: {v}' for k, v in counts.items()))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('import-legacy', help='import the old single-user config.json/passwords.json')
    p.add_argument('--from', dest='source', default='.', help='folder holding the old files (default: .)')
    p.add_argument('--user', required=True, help='Guptakosh username that will own the entries')
    p.add_argument('--vault', help="target vault name (default: the user's personal vault)")
    p.set_defaults(fn=cmd_import_legacy)
    p = sub.add_parser('backup', help='write a consistent snapshot of the database')
    p.add_argument('dest')
    p.set_defaults(fn=cmd_backup)
    sub.add_parser('verify-audit', help='check the audit log hash chain').set_defaults(fn=cmd_verify_audit)
    sub.add_parser('info', help='show record counts').set_defaults(fn=cmd_info)
    args = ap.parse_args()
    try:
        args.fn(Core(config.DATA_DIR), args)
    except AppError as e:
        sys.exit(f'Error: {e}')


if __name__ == '__main__':
    main()
