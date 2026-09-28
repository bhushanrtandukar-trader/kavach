"""Password family detection: variants of the same password, not just identical ones.

    Amazon    Kathmandu@2025
    Facebook  Kathmandu@2025!
    Gmail     Kathmandu@2026        -> one family: change one, attackers try the rest
    Instagram Kathmandu@2026!

Two passwords are family when, after folding predictable substitutions (@ -> a, 0 -> o, $ -> s ...) and
dropping digits and symbols, they share the same root — or when they are highly similar strings.  Nothing
about the root is ever returned, only *who* is in the family.
"""
import difflib
import re

_LEET = str.maketrans({'@': 'a', '$': 's', '0': 'o', '1': 'l', '3': 'e', '4': 'a', '5': 's', '7': 't', '8': 'b'})
SIMILARITY = 0.85
MAX_PAIRWISE = 400
MIN_ROOT = 5


def fold(pw: str) -> str:
    return pw.lower().translate(_LEET)


def root(pw: str) -> str:
    """The password's letters, after trimming numbers/symbols off both ends and folding substitutions:
    'Kathmandu@2025!', 'K4thmandu_2031' and 'kathmandu' all give 'kathmandu'; 'P@ssw0rd!' gives 'password'.
    (Trim first: otherwise the 0 and 4 in a year would be folded into letters.)"""
    core = re.sub(r'^[^a-zA-Z]+|[^a-zA-Z]+$', '', pw)
    return re.sub(r'[^a-z]', '', fold(core))


def _find(parent, i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _cluster(passwords):
    n = len(passwords)
    parent = list(range(n))
    by_root = {}
    for i, p in enumerate(passwords):
        r = root(p)
        if len(r) >= MIN_ROOT:
            by_root.setdefault(r, []).append(i)
    for members in by_root.values():
        for j in members[1:]:
            parent[_find(parent, j)] = _find(parent, members[0])
    if n <= MAX_PAIRWISE:
        folded = [fold(p) for p in passwords]
        for i in range(n):
            for j in range(i + 1, n):
                a, b = folded[i], folded[j]
                if abs(len(a) - len(b)) > max(len(a), len(b)) * 0.3:
                    continue
                sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
                if sm.real_quick_ratio() >= SIMILARITY and sm.quick_ratio() >= SIMILARITY and sm.ratio() >= SIMILARITY:
                    parent[_find(parent, i)] = _find(parent, j)
    groups = {}
    for i in range(n):
        groups.setdefault(_find(parent, i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]


def _differs_only_by_suffix(pws) -> bool:
    """True when the family members differ only in trailing digits/symbols (the classic 'add the year')."""
    stems = {re.sub(r'[^a-zA-Z]+$', '', p) for p in pws}
    return len(stems) == 1


def build(items):
    """items: dicts with id + password.  Returns (families, membership) where
    membership[item_id] = {'family': id, 'size': entries in family, 'others': entries with a DIFFERENT password}
    and exact_reuse[item_id] = number of OTHER entries with the identical password."""
    by_pw = {}
    for it in items:
        by_pw.setdefault(it['password'], []).append(it)
    distinct = list(by_pw)
    exact = {it['id']: len(by_pw[it['password']]) - 1 for it in items}

    clusters = [[i] for i, p in enumerate(distinct) if len(by_pw[p]) > 1]      # identical reuse on its own
    in_variant = set()
    variant_clusters = _cluster(distinct)
    for g in variant_clusters:
        in_variant.update(g)
    clusters = [c for c in clusters if c[0] not in in_variant] + variant_clusters

    families, membership = [], {}
    for n, cluster in enumerate(sorted(clusters, key=lambda c: -sum(len(by_pw[distinct[i]]) for i in c)), 1):
        members = [it for i in cluster for it in by_pw[distinct[i]]]
        pws = [distinct[i] for i in cluster]
        fid = f'f{n}'
        kind = 'identical' if len(pws) == 1 else 'variants'
        families.append({'id': fid, 'kind': kind, 'size': len(members), 'distinct': len(pws),
                         'suffix_only': kind == 'variants' and _differs_only_by_suffix(pws),
                         'members': members})
        for it in members:
            membership[it['id']] = {'family': fid, 'size': len(members),
                                    'others': sum(1 for m in members if m['password'] != it['password'])}
    return families, membership, exact
