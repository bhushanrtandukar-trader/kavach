"""Password generation and strength scoring."""
import secrets
import string


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


def password_strength(pw):
    """Returns (percent 0-100, label, bootstrap color)."""
    if not pw:
        return 0, '—', 'secondary'
    score = 0
    if len(pw) >= 8:  score += 1
    if len(pw) >= 12: score += 1
    if len(pw) >= 16: score += 1
    if any(c.isupper()             for c in pw): score += 1
    if any(c.islower()             for c in pw): score += 1
    if any(c.isdigit()             for c in pw): score += 1
    if any(c in string.punctuation for c in pw): score += 1
    if score <= 2: return score * 14, 'Weak',        'danger'
    if score == 3: return 43,         'Fair',        'warning'
    if score <= 5: return 65,         'Good',        'info'
    if score == 6: return 85,         'Strong',      'primary'
    return          100,              'Very Strong', 'success'
