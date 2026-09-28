"""Lookalike-URL detection, so a saved login is not a phishing page's address in disguise.

Runs locally on the URL text only.  Advisory: it warns, it never blocks.  Signals:

  homograph    the host uses non-ASCII characters (Cyrillic 'а' for Latin 'a', punycode ``xn--``)
  lookalike    the site name is one edit away from, or normalises to, a well-known brand
               (``paypa1.com``, ``rnicrosoft.com``, ``gooogle.com``)
  embedded     a brand name buried in a domain that is not the brand's
               (``paypal.com.secure-login.xyz``, ``apple-id-support.net``)
  other TLD    the brand's name on a different ending (``paypal.net``)
  plain http   credentials sent unencrypted
  raw IP       a bare address instead of a name
"""
import ipaddress
import unicodedata
from urllib.parse import urlsplit

BRANDS = """
google.com gmail.com youtube.com facebook.com instagram.com whatsapp.com twitter.com linkedin.com
microsoft.com live.com outlook.com office.com office365.com microsoftonline.com apple.com icloud.com
amazon.com paypal.com ebay.com netflix.com spotify.com github.com gitlab.com bitbucket.org atlassian.com
slack.com zoom.us dropbox.com salesforce.com okta.com cloudflare.com digitalocean.com heroku.com vercel.com
netlify.com stripe.com shopify.com wordpress.com godaddy.com namecheap.com adobe.com docusign.com openai.com
anthropic.com reddit.com discord.com telegram.org signal.org tiktok.com twitch.tv steampowered.com
epicgames.com binance.com coinbase.com kraken.com chase.com bankofamerica.com wellsfargo.com citi.com
americanexpress.com hsbc.com barclays.co.uk visa.com mastercard.com dhl.com fedex.com ups.com usps.com
esewa.com.np khalti.com fonepay.com connectips.com nabilbank.com nicasiabank.com globalimebank.com
nmb.com.np siddharthabank.com kumaribank.com prabhubank.com laxmisunrise.com ntc.net.np
""".split()

# Two-label public suffixes we care about (not the full Public Suffix List).
_SUFFIX2 = {'co.uk', 'org.uk', 'com.au', 'com.np', 'org.np', 'net.np', 'gov.np', 'edu.np', 'co.in', 'co.jp',
            'com.br', 'co.nz', 'com.sg', 'com.cn', 'co.za'}

# A small confusables table (Cyrillic/Greek letters that look Latin).
_CONFUSABLE = {
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x', 'і': 'i', 'ѕ': 's', 'ј': 'j', 'ԁ': 'd',
    'һ': 'h', 'ԛ': 'q', 'ԝ': 'w', 'ɡ': 'g', 'ο': 'o', 'ν': 'v', 'ρ': 'p', 'ι': 'i', 'τ': 't', 'α': 'a', 'ε': 'e',
    'κ': 'k', 'β': 'b', 'η': 'n', 'υ': 'u', 'ℓ': 'l', 'ǀ': 'l',
}
_LEET = str.maketrans({'0': 'o', '3': 'e', '4': 'a', '5': 's', '7': 't', '$': 's', '@': 'a'})


def registrable(host: str) -> str:
    labels = host.split('.')
    if len(labels) >= 3 and '.'.join(labels[-2:]) in _SUFFIX2:
        return '.'.join(labels[-3:])
    return '.'.join(labels[-2:]) if len(labels) >= 2 else host


def _sld(domain: str) -> str:
    """The name part of a registrable domain: 'paypal.com' -> 'paypal', 'esewa.com.np' -> 'esewa'."""
    return domain.split('.')[0]


def skeleton(label: str) -> str:
    """Reduce look-alike tricks to a common form: confusable letters, digits-for-letters, rn->m, vv->w."""
    out = ''.join(_CONFUSABLE.get(ch, ch) for ch in label.lower())
    out = ''.join(c for c in unicodedata.normalize('NFKD', out) if not unicodedata.combining(c))
    out = out.translate(_LEET).replace('rn', 'm').replace('vv', 'w')
    return out.replace('1', 'l')


def _skeletons(label):
    s = skeleton(label)
    return {s, s.replace('l', 'i')} if 'l' in s else {s}       # '1' can stand for l or i


def edit_distance(a: str, b: str) -> int:
    """Damerau-Levenshtein (optimal string alignment): insert, delete, substitute, swap neighbours."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


_BRAND_SET = set(BRANDS)
_BRAND_SLDS = {}
for _b in BRANDS:
    _BRAND_SLDS.setdefault(_sld(_b), []).append(_b)


def _decode_host(host: str) -> str:
    try:
        return host.encode('ascii').decode('idna') if 'xn--' in host else host
    except UnicodeError:
        return host


def check_url(url: str) -> list:
    """Returns [{'level': 'danger'|'warning', 'message': str}, ...]; empty means nothing to report."""
    url = (url or '').strip()
    if not url:
        return []
    try:
        parts = urlsplit(url if '://' in url else 'https://' + url)
        host = (parts.hostname or '').lower().rstrip('.')
    except ValueError:
        return []
    if not host or host == 'localhost' or host.endswith(('.local', '.test', '.internal', '.localhost')):
        return []
    out = []
    try:
        ipaddress.ip_address(host)
        return [{'level': 'warning', 'code': 'raw_ip', 'message': 'This address is a raw IP number, not a website name.'}]
    except ValueError:
        pass

    if parts.scheme == 'http':
        out.append({'level': 'warning', 'code': 'http', 'message': 'This address is not encrypted (http). Passwords sent to it can be read.'})

    uhost = _decode_host(host)
    dom = registrable(uhost)
    non_ascii = any(ord(c) > 127 for c in uhost)
    if dom in _BRAND_SET:
        return out                                            # exactly a known site
    name = _sld(dom)
    flagged = False
    skels = _skeletons(name)
    for brand_name, brands in _BRAND_SLDS.items():
        if len(name) < 4 or abs(len(name) - len(brand_name)) > 2:
            continue
        exact_look = brand_name in skels and name != brand_name
        close = (len(brand_name) >= 6 and any(edit_distance(s, brand_name) <= 1 for s in skels | {name})
                 and name != brand_name)
        if exact_look or close:
            out.insert(0, {'level': 'danger', 'code': 'lookalike',
                           'message': f"This looks like {brands[0]} but is a different site ({dom}). "
                                      "Check the address carefully before saving or using this login."})
            flagged = True
            break
    if not flagged and non_ascii:
        out.insert(0, {'level': 'warning', 'code': 'homograph', 'message': 'The address uses unusual (non-English) letters, which can '
                                                      'be used to imitate another site.'})
    if not flagged:
        labels = uhost.replace('-', '.').split('.')
        for brand_name, brands in _BRAND_SLDS.items():
            if len(brand_name) < 5 or name == brand_name:         # same name, other ending: handled below
                continue
            if brand_name in labels or (len(brand_name) >= 6 and brand_name in name):
                out.insert(0, {'level': 'warning', 'code': 'embedded',
                               'message': f"The address contains \"{brand_name}\" but belongs to {dom}, "
                                          f"not {brands[0]}."})
                flagged = True
                break
    if not flagged:
        for brand_name, brands in _BRAND_SLDS.items():
            if len(brand_name) >= 6 and name == brand_name:
                out.insert(0, {'level': 'warning', 'code': 'other_tld',
                               'message': f"Same name as {brands[0]} but a different ending ({dom})."})
                break
    return out


# ── risk assessment (a number, for the autofill decision engine) ─────────────────────────────────
_WEIGHTS = {'raw_ip': 45, 'lookalike': 80, 'homograph': 45, 'embedded': 60, 'other_tld': 45, 'http': 20,
            'bad_tld': 15, 'userinfo': 45, 'deep_subdomains': 10, 'long_url': 8, 'many_hyphens': 8,
            'digit_mix': 6, 'phish_words': 14}
_BAD_TLDS = {'zip', 'mov', 'top', 'xyz', 'click', 'work', 'gq', 'tk', 'ml', 'cf', 'ga', 'country', 'kim', 'loan',
             'men', 'party', 'review', 'science', 'stream', 'download', 'racing', 'win', 'bid', 'icu', 'cyou', 'rest'}
_PHISH_WORDS = ('login', 'signin', 'secure', 'verify', 'verification', 'account', 'update', 'wallet', 'support',
                'billing', 'password', 'recover', 'unlock', 'confirm', 'security')


def host_of(url: str) -> str:
    try:
        parts = urlsplit(url if '://' in (url or '') else 'https://' + (url or ''))
        return (parts.hostname or '').lower().rstrip('.')
    except ValueError:
        return ''


def assess_url(url: str) -> dict:
    """Score how much this address looks like a phishing page: {'risk': 0-99, 'signals': [...]}.

    Looks only at the URL text (offline, private). It cannot see domain age, certificates or redirects;
    those need network lookups this product deliberately does not make."""
    url = (url or '').strip()
    host = host_of(url)
    if not url or not host or host == 'localhost' or host.endswith(('.local', '.test', '.internal', '.localhost')):
        return {'risk': 0, 'signals': []}
    signals = [{'code': w.get('code', 'other'), 'weight': _WEIGHTS.get(w.get('code', ''), 30), 'message': w['message']}
               for w in check_url(url)]
    try:
        ipaddress.ip_address(host)
        return _finish(signals)
    except ValueError:
        pass
    uhost = _decode_host(host)
    dom = registrable(uhost)
    known = dom in _BRAND_SET
    labels = uhost.split('.')
    tld = labels[-1]

    def add(code, message):
        signals.append({'code': code, 'weight': _WEIGHTS[code], 'message': message})

    try:
        authority = urlsplit(url if '://' in url else 'https://' + url).netloc
        if '@' in authority:
            add('userinfo', 'The address contains "@": everything before it is ignored by the browser, a '
                            'common trick to disguise the real site.')
    except ValueError:
        pass
    if not known:
        if tld in _BAD_TLDS:
            add('bad_tld', f'".{tld}" is an ending often used for throw-away or malicious sites.')
        if len(labels) - len(dom.split('.')) >= 3:
            add('deep_subdomains', 'The address has an unusually long chain of sub-domains.')
        if uhost.count('-') >= 3:
            add('many_hyphens', 'The name is stuffed with hyphens, typical of generated look-alike domains.')
        if sum(c.isdigit() for c in _sld(dom)) >= 3 and any(c.isalpha() for c in _sld(dom)):
            add('digit_mix', 'The name mixes letters and several digits.')
        if any(w in uhost for w in _PHISH_WORDS):
            add('phish_words', 'The address uses words like "login" or "verify" on a site that is not the real one.')
    if len(url) > 120:
        add('long_url', 'The address is unusually long.')
    return _finish(signals)


def _finish(signals):
    keep = 1.0
    for s in signals:
        keep *= 1 - s['weight'] / 100
    risk = min(99, round(100 * (1 - keep)))
    signals.sort(key=lambda s: -s['weight'])
    return {'risk': risk, 'signals': signals}
