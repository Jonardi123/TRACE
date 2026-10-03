import json
from email.utils import formatdate
import pytest
import requests
from osint_workbench.search import BraveSearch, SearchError, retry_delay


class Response:
    def __init__(self, status=200, headers=None, payload=None, raw=None):
        self.status_code = status
        self.headers = headers or {}
        self.raw = raw if raw is not None else json.dumps(payload or {'web':{'results':[]}}).encode()
    def __enter__(self):
        return self
    def __exit__(self,*args):
        pass
    def iter_content(self, size):
        yield self.raw


class Session:
    def __init__(self, response=None, error=None):
        self.response = response or Response()
        self.error = error
        self.headers = {}
        self.cookies = {}
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append((url,kwargs))
        if self.error:
            raise self.error
        return self.response


def test_fixed_endpoint_filtering_and_rate_state(tmp_path):
    session = Session(Response(payload={'web':{'results':[
        {'title':'ALICE', 'url':'https://example.org/alice/', 'description':'public profile'},
        {'title':'alice_1', 'url':'https://example.org/alice_1/', 'description':'wrong handle'},
        {'title':'alice', 'url':'javascript:bad', 'description':'bad link'},
        {'title':'alice', 'url':'https://example.org/alice/', 'description':'duplicate'}]}}))
    clock = lambda:1000
    client = BraveSearch(key='fake-test-key',state_dir=tmp_path,session=session,clock=clock)
    matches,log = client.search('alice')
    assert len(matches) == 1 and log['rejected'] == 2 and log['query'] == '"alice"'
    url,kwargs = session.calls[0]
    assert url == 'https://api.search.brave.com/res/v1/web/search'
    assert kwargs['allow_redirects'] is False and kwargs['stream'] is True
    assert kwargs['params']['count'] == 20 and session.trust_env is False
    # Cooldown survives creating a new client, i.e. case switches and process restarts.
    again = BraveSearch(key='fake-test-key',state_dir=tmp_path,session=session,clock=clock)
    with pytest.raises(SearchError,match='wait'):
        again.search('alice')
    assert len(session.calls) == 1
    assert all('fake-test-key' not in p.read_text() for p in tmp_path.iterdir())


def test_retry_after_persisted_and_no_retry(tmp_path):
    session = Session(Response(status=429,headers={'Retry-After':'120'}))
    client = BraveSearch(key='fake',state_dir=tmp_path,session=session,clock=lambda:1000)
    with pytest.raises(SearchError,match='rate limit'):
        client.search('alice')
    assert json.loads(client.state_file.read_text())['next_allowed'] == 1120
    with pytest.raises(SearchError,match='wait'):
        client.search('alice')
    assert len(session.calls) == 1


@pytest.mark.parametrize('status', [301,401,403,500,503])
def test_denial_redirect_or_failure_never_falls_back(tmp_path,status):
    session = Session(Response(status=status))
    client = BraveSearch(key='fake',state_dir=tmp_path,session=session,clock=lambda:1000)
    with pytest.raises(SearchError):
        client.search('alice')
    assert len(session.calls) == 1


def test_http_date_retry_after():
    assert retry_delay(formatdate(1300,usegmt=True),lambda:1000) == 300
    assert retry_delay('invalid',lambda:1000) == 60
    assert retry_delay('-10',lambda:1000) == 60


def test_timeouts_hide_request_details(tmp_path):
    client = BraveSearch(key='fake',state_dir=tmp_path,session=Session(error=requests.Timeout('secret request content')))
    with pytest.raises(SearchError) as error:
        client.search('alice')
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('raw', [b'not-json',b'[]',b'{"web": []}',b'{"web":{"results":{}}}',b'x'*2_000_001])
def test_malformed_response(tmp_path,raw):
    client = BraveSearch(key='fake',state_dir=tmp_path,session=Session(Response(raw=raw)))
    with pytest.raises(SearchError):
        client.search('alice')


def test_corrupt_rate_state_fails_closed(tmp_path):
    session = Session()
    client = BraveSearch(key='fake',state_dir=tmp_path,session=session)
    client.state_file.write_text('bad-json')
    with pytest.raises(SearchError,match='unreadable'):
        client.search('alice')
    assert not session.calls


def test_missing_api_key_does_not_request(tmp_path,monkeypatch):
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY',raising=False)
    with pytest.raises(SearchError,match='BRAVE_SEARCH_API_KEY'):
        BraveSearch(state_dir=tmp_path)
