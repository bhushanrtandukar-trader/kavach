import string

import pytest

from guptakosh.errors import ValidationError
from guptakosh.passwords import (SYMBOLS, assess, check_master_password, generate_password,
                                 password_strength)


@pytest.mark.parametrize('length', [4, 12, 24, 128])
def test_generator_meets_length_and_contains_every_enabled_class(length):
    for _ in range(30):
        p = generate_password(length)
        assert len(p) == max(length, 4)
        assert any(c.isupper() for c in p) and any(c.islower() for c in p)
        assert any(c.isdigit() for c in p) and any(c in SYMBOLS for c in p)


def test_generator_options():
    p = generate_password(40, digits=False, symbols=False)
    assert len(p) == 40 and p.isalpha() and any(c.isupper() for c in p) and any(c.islower() for c in p)
    for _ in range(50):
        q = generate_password(30, ambiguous=False)
        assert not set('O0oIl1|') & set(q)
        assert any(c.isdigit() for c in q) and any(c in SYMBOLS for c in q)


def test_generator_is_random():
    assert len({generate_password(20) for _ in range(200)}) == 200


def test_assess_and_labels():
    assert assess('')['score'] == 0
    weak, strong = assess('password123'), assess('xK9#mQ2$vL7@pR4!')
    assert weak['score'] <= 1 and weak['warning'] and strong['score'] == 4
    assert password_strength('')[1] == '—'
    assert password_strength('xK9#mQ2$vL7@pR4!')[1] == 'Very strong'
    assert password_strength('password123')[2] == 'danger'


def test_personal_details_lower_the_score():
    assert assess('olivia-acme-2024', ['olivia', 'acme'])['score'] < assess('olivia-acme-2024')['score']


def test_master_password_rules():
    check_master_password('correct-horse-battery-1', 12, ['olivia'])
    for bad in ('short', 'password123456', 'aaaaaaaaaaaaaaaa', 'olivia-loves-vaults-1'):
        with pytest.raises(ValidationError):
            check_master_password(bad, 12, ['olivia'])
    with pytest.raises(ValidationError):
        check_master_password('x' * 300, 12)
