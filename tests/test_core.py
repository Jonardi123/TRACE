import pytest
from osint_workbench.core import Case, public_url, timestamp, username
from osint_workbench.search import exact_match, browser_search_url


@pytest.mark.parametrize('value,expected', [(' @Alice_1 ', 'alice_1'), ('a.b','a.b')])
def test_username_normalizes(value, expected):
    assert username(value) == expected


@pytest.mark.parametrize('value', ['', 'x'*31, 'bad name', '../bad', 'a" OR something', 'https://instagram.com/user'])
def test_username_rejects_query_injection(value):
    with pytest.raises(ValueError):
        username(value)


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'file:///etc/passwd', 'https://u:p@example.org',
    'http://127.0.0.1/', 'http://[::1]/', 'http://10.0.0.1/', 'https://localhost/', 'https://foo.local/',
    'https://example.org:8080/', 'https://example.org/\nmalicious', 'https://example.org\\evil'])
def test_invalid_links(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_public_links():
    assert public_url('https://example.org/test?q=1&x=2') == 'https://example.org/test?q=1&x=2'


def test_timezones_are_not_guessed():
    assert timestamp('2026-01-01T12:00:00') is None
    assert timestamp('2026-01-01T12:00:00+02:00') == '2026-01-01T10:00:00.000+00:00'
    assert timestamp('garbage') is None
    assert timestamp(0, milliseconds=True) == '1970-01-01T00:00:00.000+00:00'
    assert timestamp(10**100, milliseconds=True) is None


@pytest.mark.parametrize('candidate', ['alice1', 'alice_1', 'malice', 'alice.name'])
def test_exact_match_rejects_substrings(candidate):
    assert not exact_match('alice', candidate, f'https://example.org/{candidate}', candidate)[0]


def test_exact_match_path_and_mentions():
    assert exact_match('alice.1', '', 'https://example.org/%61lice.1/', '')[0]
    yes, basis = exact_match('alice', 'Post about <b>@ALICE</b>', 'https://example.org/post', '')
    assert yes and 'mention' in basis
    assert not exact_match('alice', '', 'https://alice.example.org/', '')[0]


def test_browser_query_quoted():
    assert browser_search_url('alice.1') == 'https://duckduckgo.com/?q=%22alice.1%22'


def test_case_round_trip():
    case = Case('alice')
    assert Case.from_dict(case.to_dict()) == case
    with pytest.raises(ValueError):
        Case.from_dict({'schema_version': 9})


@pytest.mark.parametrize('url',['http://127.1/', 'http://127.000.000.001/', 'http://2130706433/'])
def test_ambiguous_numeric_hosts_rejected(url):
    with pytest.raises(ValueError):
        public_url(url)


@pytest.mark.parametrize('data',[[], {'schema_version':1}, {'schema_version':1,'username':'alice','messages':[1]}])
def test_malformed_cases_give_clear_errors(data):
    with pytest.raises(ValueError):
        Case.from_dict(data)
