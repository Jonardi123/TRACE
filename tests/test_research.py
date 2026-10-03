import json
import pytest
from test_search import Response, Session
from osint_workbench.core import Case, PublicResult, now
from osint_workbench.research import PublicResearch, record_research
from osint_workbench.storage import load_case, save_case


def github_payload(handle='alice', **extra):
    return dict(login=handle, html_url=f'https://github.com/{handle}', public_repos=3, followers=2,
                email='SHOULD_NOT_BE_RETAINED@example.org', location='SHOULD_NOT_BE_RETAINED',
                avatar_url='https://example.org/unfetched', **extra)


def client(tmp_path, response):
    session=Session(response)
    return PublicResearch(state_dir=tmp_path,session=session,clock=lambda:1000),session


def test_key_free_exact_lookup_strips_contacts_and_auth(tmp_path):
    research,session=client(tmp_path,Response(payload=github_payload()))
    assert session.headers == {} and session.cookies == {}
    result=research.lookup('alice','GitHub')
    assert result.status=='exact_public_handle' and result.fields=={'public_repos':3,'followers':2}
    assert 'SHOULD_NOT_BE_RETAINED' not in json.dumps(result.__dict__)
    assert result.profile_url=='https://github.com/alice' and len(result.response_sha256)==64
    url,arguments=session.calls[0]
    assert url=='https://api.github.com/users/alice' and not arguments['allow_redirects']
    assert arguments['params'] is None and session.trust_env is False
    assert 'Authorization' not in arguments['headers']
    assert 'No evidence links' in result.detail


def test_gitlab_exact_query_and_source(tmp_path):
    research,session=client(tmp_path,Response(payload=[{'username':'ALICE','web_url':'https://gitlab.com/alice','email':'omit'}]))
    result=research.lookup('alice','GitLab')
    assert result.status=='exact_public_handle' and result.fields=={}
    assert session.calls[0][1]['params']=={'username':'alice','per_page':1}
    assert '?username=alice&per_page=1' in result.request_url


@pytest.mark.parametrize('response,status', [(Response(status=404),'no_exact_result'),(Response(status=429),'rate_limited'),
    (Response(status=403),'unavailable'),(Response(status=301),'unavailable'),(Response(status=503),'unavailable'),
    (Response(raw=b'[]'),'no_exact_result')])
def test_degraded_results_are_honest(tmp_path,response,status):
    research,session=client(tmp_path,response)
    result=research.lookup('alice','GitLab')
    assert result.status==status and not result.profile_url and not result.fields
    assert len(session.calls)==1


@pytest.mark.parametrize('payload', [github_payload('bob'),github_payload(html_url_override='irrelevant'),
    {'login':'alice','html_url':'https://evil.example/alice'},
    {'login':'alice','html_url':'https://github.com/bob'},[],{'login':False}])
def test_unexpected_profiles_never_become_matches(tmp_path,payload):
    if isinstance(payload,dict) and 'html_url_override' in payload:
        payload['html_url']='https://github.com/alice/other'
    research,session=client(tmp_path,Response(payload=payload,raw=json.dumps(payload).encode()))
    result=research.lookup('alice','GitHub')
    assert result.status=='unavailable' and not result.profile_url


def test_retry_after_and_quota_reset_persist_between_clients(tmp_path):
    response=Response(status=403,headers={'Retry-After':'120','X-RateLimit-Remaining':'0','X-RateLimit-Reset':'1500'})
    research,session=client(tmp_path,response)
    assert research.lookup('alice','GitHub').status=='rate_limited'
    assert json.loads((tmp_path/'public-github.json').read_text())['next_allowed']==1500
    another=PublicResearch(state_dir=tmp_path,session=session,clock=lambda:1100)
    assert another.lookup('alice','GitHub').status=='rate_limited' and len(session.calls)==1


@pytest.mark.parametrize('handle',['alice.name','alice_1'])
def test_unsupported_handle_is_not_a_claim_of_absence(tmp_path,handle):
    research,session=client(tmp_path,Response())
    result=research.lookup(handle,'GitHub')
    assert result.status=='unsupported_handle' and not session.calls


@pytest.mark.parametrize('raw',[b'bad json',b'x'*1_000_001,b'null'])
def test_bad_or_large_response(tmp_path,raw):
    research,session=client(tmp_path,Response(raw=raw))
    assert research.lookup('alice','GitHub').status=='unavailable'


@pytest.mark.parametrize('state',['[]','{"next_allowed":NaN}','not-json'])
def test_bad_cooldown_state_fails_closed(tmp_path,state):
    research,session=client(tmp_path,Response())
    (tmp_path/'public-github.json').write_text(state)
    assert research.lookup('alice','GitHub').status=='unavailable' and not session.calls


def test_prior_success_retained_when_recheck_is_unavailable(tmp_path):
    case=Case('alice');save_case(case,tmp_path/'case')
    good=PublicResult('GitHub','alice','exact_public_handle',now(),'https://api.github.com/users/alice',
                      profile_url='https://github.com/alice',returned_username='alice')
    record_research(case,tmp_path/'case',[good])
    bad=PublicResult('GitHub','alice','unavailable',now(),'https://api.github.com/users/alice',detail='HTTP 503')
    record_research(case,tmp_path/'case',[bad])
    assert case.public_results==[good] and case.audit_log[-1]['status']=='unavailable'
    assert load_case(tmp_path/'case').public_results==[good]
    with pytest.raises(ValueError):
        record_research(case,tmp_path/'case',[PublicResult('GitHub','bob','unavailable',now(),'https://api.github.com/users/bob')])
