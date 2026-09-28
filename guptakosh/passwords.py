"""Password generation and strength estimation."""
import secrets
import string

from zxcvbn import zxcvbn

from .errors import ValidationError

MIN_MASTER_SCORE = 3      # zxcvbn 0-4; 3 = "safely unguessable" against offline attacks


def generate_password(length: int = 16) -> str:
    length = max(length, 4)
    upper, lower = string.ascii_uppercase, string.ascii_lowercase
    digits, specials = string.digits, '_@#!'
    pool = upper + lower + digits + specials
    pwd = [secrets.choice(upper), secrets.choice(lower),
           secrets.choice(digits), secrets.choice(specials)]
    pwd += [secrets.choice(pool) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return ''.join(pwd)


def assess(pw: str, user_inputs=()) -> dict:
    """Pattern-based strength estimate (zxcvbn): dictionary words, keyboard walks, dates,
    l33t substitutions, repeats and sequences are all modelled, unlike a rule checklist.

    Returns {'score': 0-4, 'guesses_log10': float, 'crack_time': str, 'warning': str, 'suggestions': [..]}.
    """
    pw = (pw or '')[:256]                       # zxcvbn is slow on very long input
    inputs = [s for s in (user_inputs or ()) if s]
    r = zxcvbn(pw, user_inputs=inputs) if pw else None
    if r is None:
        return {'score': 0, 'guesses_log10': 0.0, 'crack_time': '', 'warning': '', 'suggestions': []}
    fb = r.get('feedback', {})
    return {'score': r['score'], 'guesses_log10': r['guesses_log10'],
            'crack_time': r['crack_times_display']['offline_slow_hashing_1e4_per_second'],
            'warning': fb.get('warning', ''), 'suggestions': fb.get('suggestions', [])}


_LABELS = {0: ('Very weak', 'danger', 12), 1: ('Weak', 'danger', 30), 2: ('Fair', 'warning', 55),
           3: ('Strong', 'info', 80), 4: ('Very strong', 'success', 100)}


def password_strength(pw, user_inputs=()):
    """For the UI meter: (percent, label, bootstrap colour)."""
    if not pw:
        return 0, '—', 'secondary'
    label, color, pct = _LABELS[assess(pw, user_inputs)['score']]
    return pct, label, color


def check_master_password(pw: str, min_length: int = 12, user_inputs=()):
    """Raise ValidationError unless `pw` is acceptable as a master password."""
    if not pw or len(pw) < min_length:
        raise ValidationError(f'Password must be at least {min_length} characters.')
    if len(pw) > 256:
        raise ValidationError('Password is too long (max 256).')
    low = pw.lower()
    for s in user_inputs:
        s = (s or '').strip().lower()
        if len(s) >= 4 and s in low:
            raise ValidationError('Password must not contain your name, username or organisation.')
    a = assess(pw, user_inputs)
    if a['score'] < MIN_MASTER_SCORE:
        hint = a['warning'] or (a['suggestions'][0] if a['suggestions'] else 'Add more unrelated words.')
        raise ValidationError(f'That password is too easy to guess. {hint}')
