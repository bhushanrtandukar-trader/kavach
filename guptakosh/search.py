"""Typo-tolerant search over entry metadata (service, username, URL, notes).  Never touches passwords.

Every word of the query must match something: exact substring (best), word prefix, or a fuzzy match by
character-trigram overlap / sequence similarity, so "gthub", "amzon" or "netflx" still find the right entry.
Results are ranked best-first.
"""
import difflib
import re
import unicodedata

THRESHOLD = 0.6
FIELD_WEIGHT = {'service': 1.0, 'username': 0.9, 'url': 0.9, 'notes': 0.8}


def _norm(text: str) -> str:
    text = unicodedata.normalize('NFKD', (text or '').lower())
    return ''.join(c for c in text if not unicodedata.combining(c))


def _words(text: str):
    return re.findall(r'[a-z0-9]+', _norm(text))


def _trigrams(word: str) -> set:
    padded = f'  {word} '
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


def _token_score(token: str, field_text: str, words) -> float:
    if token in _norm(field_text):
        return 1.0
    best = 0.0
    tg = _trigrams(token)
    for w in words:
        if w.startswith(token):
            return 0.95
        if len(token) < 3:
            continue
        overlap = len(tg & _trigrams(w)) / len(tg | _trigrams(w))
        ratio = difflib.SequenceMatcher(None, token, w).ratio()
        best = max(best, overlap * 0.9 if overlap >= 0.4 else 0.0, ratio * 0.9 if ratio >= 0.75 else 0.0)
    return best


def score(entry: dict, query: str) -> float:
    tokens = _words(query)
    if not tokens:
        return 1.0
    fields = [(FIELD_WEIGHT[k], entry.get(k, ''), _words(entry.get(k, ''))) for k in FIELD_WEIGHT]
    total = 0.0
    for t in tokens:
        best = max((w * _token_score(t, text, words) for w, text, words in fields), default=0.0)
        if best < THRESHOLD:
            return 0.0                                            # every query word must match something
        total += best
    return total / len(tokens)


def rank(entries, query: str):
    """Entries that match `query`, best first (stable for ties).  An empty query returns everything."""
    if not _words(query):
        return list(entries)
    scored = [(score(e, query), i, e) for i, e in enumerate(entries)]
    return [e for s, i, e in sorted((x for x in scored if x[0] > 0), key=lambda x: (-x[0], x[1]))]
