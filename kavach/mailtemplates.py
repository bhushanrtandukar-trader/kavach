"""The words of every email Kavach sends.  Pure functions: (facts in) -> (subject, plain text, HTML).

Two rules keep these safe to send.  They never contain a password, a vault entry or a key; the invite code
is the only secret, and it is single-use and expires.  And alerts carry no links, so a real alert cannot be
mistaken for (or imitated by) a phishing message asking you to "click to secure your account".
"""
from datetime import datetime
from html import escape

ACCENT = '#5b3fd6'


def _when(ts) -> str:
    return datetime.fromtimestamp(ts).strftime('%d %b %Y, %H:%M') if ts else 'just now'


def _shell(org: str, heading: str, paragraphs, foot: str = '', code: str = '', link: str = '', rows=()) -> str:
    """One layout for every message: inline styles only (mail clients ignore stylesheets)."""
    body = ''.join(f'<p style="margin:0 0 14px;line-height:1.55">{escape(p)}</p>' for p in paragraphs)
    if code:
        body += (f'<p style="margin:18px 0"><span style="display:inline-block;padding:12px 16px;border-radius:10px;'
                 f'background:#f1eefc;font-family:Consolas,Menlo,monospace;font-size:16px;letter-spacing:.5px;'
                 f'word-break:break-all">{escape(code)}</span></p>')
    if rows:
        cells = ''.join(f'<tr><td style="padding:6px 16px 6px 0;color:#666;white-space:nowrap">{escape(k)}</td>'
                        f'<td style="padding:6px 0">{escape(str(v))}</td></tr>' for k, v in rows)
        body += f'<table style="border-collapse:collapse;margin:0 0 14px;font-size:14px">{cells}</table>'
    if link:
        body += (f'<p style="margin:18px 0"><a href="{escape(link, quote=True)}" style="background:{ACCENT};color:#fff;'
                 f'text-decoration:none;padding:11px 20px;border-radius:9px;display:inline-block">Open Kavach</a></p>')
    footer = f'<p style="margin:22px 0 0;font-size:12px;color:#888;line-height:1.5">{escape(foot)}</p>' if foot else ''
    return (f'<!doctype html><html><body style="margin:0;padding:24px;background:#f6f5fb;'
            f'font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1c1b22"><div style="max-width:540px;margin:0 auto;'
            f'background:#fff;border-radius:16px;padding:28px 30px;border:1px solid #e7e4f4">'
            f'<div style="font-size:13px;font-weight:600;color:{ACCENT};margin-bottom:14px">Kavach · {escape(org)}</div>'
            f'<h1 style="font-size:20px;margin:0 0 16px">{escape(heading)}</h1>{body}{footer}</div></body></html>')


def _text(org, heading, paragraphs, code='', link='', rows=(), foot='') -> str:
    parts = [f'Kavach — {org}', '', heading, '']
    parts += [p + '\n' for p in paragraphs]
    if code:
        parts += [f'    {code}', '']
    if rows:
        parts += [f'  {k}: {v}' for k, v in rows] + ['']
    if link:
        parts += [link, '']
    if foot:
        parts += ['--', foot]
    return '\n'.join(parts).rstrip() + '\n'


def _make(org, subject, heading, paragraphs, *, code='', link='', rows=(), foot=''):
    return (subject, _text(org, heading, paragraphs, code, link, rows, foot),
            _shell(org, heading, paragraphs, foot, code, link, rows))


# ── invitations ──────────────────────────────────────────────────────────
def invite(org, name, username, code, hours, link, inviter=''):
    who = f'{inviter} has' if inviter else 'You have'
    return _make(
        org, f'You have been invited to {org} on Kavach', f'Welcome, {name}',
        [f'{who} invited you to {org} on Kavach, a password manager for your team.',
         f'Open Kavach, choose "Activate your account", and enter your username ({username}) and this one-time '
         f'invite code. You will then choose your own master password; nobody else ever knows it.'],
        code=code, link=link,
        foot=f'The code works once and expires in {hours} hours. Kavach will never email you a password. '
             f'If you were not expecting this, ignore it.')


# ── security alerts ──────────────────────────────────────────────────────
ALERT_FOOT = ('If this was you, no action is needed. If it was not, change your master password now and tell '
              'your administrator. Kavach never asks for your password by email.')


def alert(kind, org, name, **f):
    ip = f.get('ip') or 'unknown'
    when = _when(f.get('ts'))
    rows = [('When', when), ('From address', ip)]
    if kind == 'new_signin':
        return _make(org, f'New sign-in to your {org} Kavach account', 'Sign-in from a new address',
                     [f'Hi {name}, your account was just signed in to from an address it has not used before.'],
                     rows=rows + ([('Using', f['client'])] if f.get('client') else []), foot=ALERT_FOOT)
    if kind == 'locked':
        return _make(org, f'Your {org} Kavach account was locked', 'Too many failed sign-ins',
                     [f'Hi {name}, someone entered the wrong password or code several times, so the account is '
                      f'locked for {f.get("minutes", 5)} minutes.'], rows=rows, foot=ALERT_FOOT)
    if kind == 'password_changed':
        return _make(org, f'Your {org} Kavach master password was changed', 'Master password changed',
                     [f'Hi {name}, the master password for your account was changed and every other signed-in '
                      f'device was signed out.'], rows=rows, foot=ALERT_FOOT)
    if kind == 'mfa_enabled':
        return _make(org, f'Two-factor turned on for your {org} Kavach account', 'Two-factor turned on',
                     [f'Hi {name}, two-factor authentication is now on for your account.'], rows=rows,
                     foot=ALERT_FOOT)
    if kind == 'mfa_disabled':
        return _make(org, f'Two-factor turned off for your {org} Kavach account', 'Two-factor turned off',
                     [f'Hi {name}, two-factor authentication was turned off for your account.'], rows=rows,
                     foot=ALERT_FOOT)
    if kind == 'mfa_reset':
        return _make(org, f'Two-factor reset on your {org} Kavach account', 'Two-factor reset by an administrator',
                     [f'Hi {name}, an administrator reset two-factor authentication on your account, so you can '
                      f'sign in with just your password until you set it up again. Please do that soon.'],
                     rows=[('When', when)],
                     foot='If you did not ask for this, tell your administrator.')
    if kind == 'email_changed':
        new = f.get('new_email') or 'a different address'
        return _make(org, f'The email on your {org} Kavach account was changed', 'Account email changed',
                     [f'Hi {name}, security emails for your account will now go to {new} instead of this address.'],
                     rows=rows, foot=ALERT_FOOT)
    raise ValueError(f'unknown alert: {kind}')


# ── the test message and the weekly digest ───────────────────────────────
def test(org, name):
    return _make(org, 'Kavach test email', 'Email delivery works',
                 [f'Hi {name}, this is a test message from your Kavach server. If you can read it, invites, security '
                  f'alerts and the weekly digest will reach people.'])


SEV_LABEL = {'high': 'HIGH', 'medium': 'MEDIUM', 'low': 'LOW'}


def digest(org, name, d):
    """d: the dict built by Accounts.digest_data()."""
    days = d['days']
    findings = d['findings']
    high = sum(1 for x in findings if x['severity'] == 'high')
    subject = (f'{org}: {high} high-severity finding{"s" if high != 1 else ""} this week' if high
               else f'{org}: your weekly Kavach security summary')
    paras = [f'Hi {name}, here is what happened in the last {days} days.']
    if findings:
        paras.append(f'{len(findings)} thing{"s" if len(findings) != 1 else ""} to look at, worst first:')
    else:
        paras.append('Nothing unusual was found in the audit log.')
    for x in findings[:8]:
        paras.append(f'[{SEV_LABEL.get(x["severity"], x["severity"]).upper()}] {x["title"]} — {x["detail"]}')
    if len(findings) > 8:
        paras.append(f'…and {len(findings) - 8} more in the Security page.')
    rows = [('Active people', d['active']), ('Pending invites', d['pending_invites'])]
    if d['expired_invites']:
        rows.append(('Expired invites', d['expired_invites']))
    rows.append(('Without two-factor', f'{len(d["no_mfa"])}' + (f' ({", ".join(d["no_mfa"][:6])}'
                                                                   f'{"…" if len(d["no_mfa"]) > 6 else ""})'
                                                                   if d['no_mfa'] else '')))
    if d['rotation_pending']:
        rows.append(('Vaults awaiting key rotation', d['rotation_pending']))
    rows.append(('Audit log integrity', 'intact' if d['audit_ok'] else f'BROKEN at entry {d["audit_bad_id"]}'))
    return _make(org, subject, f'Weekly security summary', paras, rows=rows,
                 foot='You get this because you are an owner or administrator. It can be switched off under '
                      'People & policy → Security policy.')
