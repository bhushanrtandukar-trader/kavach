"""How much does it hurt if this account is taken over?  Transparent keyword rules, not a black box.

The category gives an *impact* weight (0-1) used to rank what to fix first: a weak password on a bank
account matters far more than one on a forum.  It is inferred from the service name and URL only.
"""
import re
from urllib.parse import urlsplit

CATEGORIES = {
    'cloud':    {'label': 'Cloud & infrastructure', 'impact': 0.90, 'phrase': 'a cloud/infrastructure account'},
    'banking':  {'label': 'Financial',              'impact': 1.00, 'phrase': 'a financial account'},
    'identity': {'label': 'Identity & email',       'impact': 1.00, 'phrase': 'an identity/email account'},
    'dev':      {'label': 'Developer tools',        'impact': 0.75, 'phrase': 'a developer account'},
    'work':     {'label': 'Work & collaboration',   'impact': 0.65, 'phrase': 'a work account'},
    'social':   {'label': 'Social',                 'impact': 0.50, 'phrase': 'a social account'},
    'shopping': {'label': 'Shopping & media',       'impact': 0.35, 'phrase': 'a shopping/media account'},
    'other':    {'label': 'Other',                  'impact': 0.30, 'phrase': 'an account'},
}

# Checked in this order: the first category with a hit wins (so "AWS console" is cloud, not shopping).
_KEYWORDS = {
    'cloud': ['aws', 'azure', 'gcp', 'cloud', 'digitalocean', 'heroku', 'vercel', 'netlify', 'cloudflare', 'server',
              'ssh', 'vpn', 'prod', 'database', 'kubernetes', 'root', 'firewall', 'hosting', 'domain registrar',
              'namecheap', 'godaddy'],
    'banking': ['bank', 'paypal', 'esewa', 'khalti', 'fonepay', 'connectips', 'wise', 'revolut', 'stripe', 'visa',
                'mastercard', 'amex', 'chase', 'hsbc', 'citi', 'wells', 'loan', 'credit', 'invest', 'broker',
                'trading', 'crypto', 'coinbase', 'binance', 'kraken', 'wallet', 'tax', 'insurance', 'payroll',
                'nabil', 'nmb', 'siddhartha', 'prabhu', 'laxmi', 'finance'],
    'identity': ['gmail', 'google', 'outlook', 'hotmail', 'live.com', 'yahoo', 'icloud', 'proton', 'mail',
                 'apple id', 'microsoft', 'office365', 'okta', 'auth0', 'sso', 'identity', 'passport'],
    'dev': ['github', 'gitlab', 'bitbucket', 'npm', 'pypi', 'docker', 'sentry', 'jenkins', 'atlassian', 'jira',
            'circleci', 'travis'],
    'work': ['slack', 'zoom', 'notion', 'teams', 'asana', 'trello', 'confluence', 'hubspot', 'salesforce',
             'zendesk', 'figma', 'canva', 'dropbox', 'intranet', 'payroll portal'],
    'social': ['facebook', 'instagram', 'twitter', 'linkedin', 'tiktok', 'reddit', 'discord', 'snapchat',
               'whatsapp', 'telegram', 'pinterest', 'youtube', 'forum'],
    'shopping': ['amazon', 'ebay', 'netflix', 'spotify', 'aliexpress', 'daraz', 'etsy', 'shop', 'store',
                 'flipkart', 'hulu', 'disney', 'prime'],
}
_SHORT = {'aws', 'gcp', 'vpn', 'ssh', 'npm', 'sso', 'tax', 'nmb', 'prod', 'root', 'wise', 'citi', 'visa', 'amex'}


def _hits(text: str, kw: str) -> bool:
    return bool(re.search(rf'\b{re.escape(kw)}\b', text)) if kw in _SHORT else kw in text


def categorize(service: str, url: str = '') -> str:
    host = ''
    if url:
        try:
            host = (urlsplit(url if '://' in url else 'https://' + url).hostname or '').lower()
        except ValueError:
            host = ''
    text = f'{(service or "").lower()} {host}'
    for cat, words in _KEYWORDS.items():
        if any(_hits(text, w) for w in words):
            return cat
    return 'other'


def impact(category: str) -> float:
    return CATEGORIES[category]['impact']
