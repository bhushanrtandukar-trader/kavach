import pytest

from kavach import phishing, search


def levels(url):
    return [w['level'] for w in phishing.check_url(url)]


# ── phishing ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize('url', [
    'https://github.com/login', 'https://accounts.google.com', 'https://www.paypal.com/signin',
    'github.com', 'https://console.aws.amazon.com', 'https://esewa.com.np', 'https://stackoverflow.com',
    'https://en.wikipedia.org/wiki/X', 'https://mycompany.com', 'https://apples-orchard.com',
    'https://learn.microsoft.com', 'http://localhost:8050', 'https://vault.corp.test', '', '   ', 'not a url at all',
    'https://intranet', 'ftp://', 'https://[::1]/x',
])
def test_legitimate_or_unknown_urls_are_quiet(url):
    assert [w for w in phishing.check_url(url) if w['level'] == 'danger'] == []


@pytest.mark.parametrize('url', [
    'https://paypa1.com', 'https://paypaI.com', 'https://rnicrosoft.com', 'https://gooogle.com',
    'https://githbu.com', 'https://amaz0n.com', 'https://netfIix.com', 'https://faceb00k.com',
    'https://аpple.com',                       # Cyrillic 'a'
    'https://xn--pple-43d.com',                     # the same thing, punycode
    'https://gооgle.com',                 # two Cyrillic 'o'
    'https://esewa-np.com/x' if False else 'https://e5ewa.com.np',
])
def test_lookalikes_are_danger(url):
    assert 'danger' in levels(url), phishing.check_url(url)


def test_warning_names_the_real_brand():
    (w,) = phishing.check_url('https://paypa1.com')
    assert 'paypal.com' in w['message'] and 'paypa1.com' in w['message']


def test_brand_buried_in_another_domain():
    w = phishing.check_url('https://paypal.com.secure-login.xyz/signin')
    assert w and w[0]['level'] == 'warning' and 'secure-login.xyz' in w[0]['message']
    assert phishing.check_url('https://apple-id-support.net')[0]['level'] == 'warning'


def test_same_name_other_tld():
    w = phishing.check_url('https://paypal.net')
    assert w and 'different ending' in w[0]['message']


def test_plain_http_and_raw_ip():
    assert levels('http://github.com/login') == ['warning']
    assert levels('http://192.168.1.10/admin') == ['warning']
    assert 'raw IP' in phishing.check_url('https://8.8.8.8')[0]['message']


def test_non_ascii_without_a_brand_is_only_a_warning():
    assert levels('https://café-de-paris.com') == ['warning']


def test_edit_distance_and_skeleton():
    assert phishing.edit_distance('paypal', 'paypa1') == 1
    assert phishing.edit_distance('google', 'goggle') == 1
    assert phishing.edit_distance('github', 'gtihub') == 1            # neighbour swap counts once
    assert phishing.edit_distance('abc', 'xyz') == 3
    assert 'microsoft' in phishing._skeletons('rnicrosoft')
    assert 'paypal' in phishing._skeletons('paypa1')


def test_registrable_domain():
    assert phishing.registrable('a.b.example.com') == 'example.com'
    assert phishing.registrable('www.esewa.com.np') == 'esewa.com.np'
    assert phishing.registrable('localhost') == 'localhost'


# ── search ───────────────────────────────────────────────────────────────
E = [{'service': 'GitHub', 'username': 'ops@acme.test', 'url': 'https://github.com', 'notes': 'org admin'},
     {'service': 'Amazon Web Services', 'username': 'root', 'url': '', 'notes': 'prod account'},
     {'service': 'Netflix', 'username': 'family', 'url': '', 'notes': ''},
     {'service': 'Bank portal', 'username': 'olivia', 'url': 'https://nabilbank.com', 'notes': 'PIN in safe'},
     {'service': 'Jenkins', 'username': 'admin', 'url': '', 'notes': 'CI server'}]


def names(q):
    return [e['service'] for e in search.rank(E, q)]


def test_empty_query_returns_everything_in_order():
    assert names('') == [e['service'] for e in E] and names('   ') == names('')


@pytest.mark.parametrize('typo, expected', [('gthub', 'GitHub'), ('githbu', 'GitHub'), ('netflx', 'Netflix'),
                                            ('jenkin', 'Jenkins'), ('amzon', 'Amazon Web Services'),
                                            ('nabil', 'Bank portal'), ('bnk', 'Bank portal')])
def test_typos_still_find_the_entry(typo, expected):
    assert names(typo)[0] == expected


def test_all_words_must_match():
    assert names('aws prod') == []                     # 'aws' is not in the text; no partial credit
    assert names('amazon prod') == ['Amazon Web Services']
    assert names('web services') == ['Amazon Web Services']


def test_unrelated_query_finds_nothing():
    assert names('zzzzqqq') == [] and names('spotify') == []


def test_exact_ranks_before_fuzzy():
    entries = [{'service': 'Gitlab', 'username': '', 'url': '', 'notes': ''},
               {'service': 'GitHub', 'username': '', 'url': '', 'notes': ''}]
    assert [e['service'] for e in search.rank(entries, 'github')][0] == 'GitHub'


def test_searches_other_fields_but_never_passwords():
    assert names('ci server') == ['Jenkins'] and names('safe') == ['Bank portal']
    e = [{'service': 'X', 'username': '', 'url': '', 'notes': '', 'password': 'hunter2-secret'}]
    assert search.rank(e, 'hunter2') == []


def test_accents_and_case_are_ignored():
    assert search.rank([{'service': 'Café Portal'}], 'CAFE') != []
