"""Exact public handles through official unauthenticated APIs; never identity linkage."""
import hashlib
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit

import requests
from filelock import FileLock

from .core import PublicResult, now, public_url, username
from .paths import rate_state_directory
from .search import retry_delay
from .storage import atomic_write, commit_case

PROVIDERS = ('GitHub', 'GitLab')
LIMITATION = ('Exact public handle only. No evidence links this profile to the Instagram account or to a real-world identity. '
              'Coverage is limited to the selected providers and the time of the request.')


class PublicResearch:
    def __init__(self, *, state_dir=None, session=None, clock=time.time):
        self.clock = clock
        self.state_dir = Path(state_dir) if state_dir else rate_state_directory()
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.session.headers.clear()
        self.session.cookies.clear()

    def lookup(self, handle, provider):
        handle = username(handle)
        if provider not in PROVIDERS:
            raise ValueError('Choose GitHub or GitLab; custom endpoints are not supported.')
        if provider == 'GitHub':
            request_url = f'https://api.github.com/users/{handle}'
            params = None
        else:
            request_url = 'https://gitlab.com/api/v4/users'
            params = {'username': handle, 'per_page': 1}
        record = PublicResult(provider, handle, 'unavailable', now(),
                              request_url + ('?' + urlencode(params) if params else ''))
        if provider == 'GitHub' and not re.fullmatch(r'[a-z0-9]+', handle):
            record.status = 'unsupported_handle'
            record.detail = 'The exact Instagram handle contains punctuation GitHub does not accept. No request made.'
            return record
        lock_path = self.state_dir / f'public-{provider.lower()}.lock'
        state_path = self.state_dir / f'public-{provider.lower()}.json'
        with FileLock(lock_path, timeout=30, mode=0o600):
            try:
                state = json.loads(state_path.read_text()) if state_path.exists() else {}
                next_allowed = float(state.get('next_allowed', 0))
                if not math.isfinite(next_allowed):
                    raise ValueError('Non-finite rate state')
                wait = next_allowed - self.clock()
            except (AttributeError, ValueError, TypeError, OSError):
                record.detail = 'Local rate state is unreadable; no request made.'
                return record
            if wait > 0:
                record.status = 'rate_limited'
                record.detail = f'Local cooldown: wait {math.ceil(wait)} seconds. No request made.'
                return record
            deadline = self.clock() + 60
            self._save(state_path, deadline)
            try:
                # Credentials, environment proxies and cookies are never used.
                self.session.cookies.clear()
                with self.session.get(request_url, params=params,
                        headers={'Accept': 'application/json', 'User-Agent': 'TRACE/0.2 (public evidence research)'},
                        timeout=(5, 15), stream=True, allow_redirects=False) as response:
                    record.checked_at = now()
                    cooldown = self.clock() + 60
                    if response.headers.get('Retry-After'):
                        cooldown = max(cooldown, self.clock() + retry_delay(response.headers['Retry-After'], self.clock))
                    if response.headers.get('X-RateLimit-Remaining', response.headers.get('RateLimit-Remaining')) == '0':
                        reset = response.headers.get('X-RateLimit-Reset', response.headers.get('RateLimit-Reset'))
                        try:
                            reset = float(reset)
                            if math.isfinite(reset):
                                cooldown = max(cooldown, reset)
                        except (TypeError, ValueError):
                            pass
                    self._save(state_path, cooldown)
                    code = response.status_code
                    if code in (403, 429):
                        record.status = 'rate_limited' if code == 429 or response.headers.get('X-RateLimit-Remaining') == '0' else 'unavailable'
                        record.detail = f'HTTP {code}: access denied or quota reached. No retry or fallback attempted; absence is not established.'
                        return record
                    if code == 404:
                        record.status = 'no_exact_result'
                        record.detail = 'Public API returned HTTP 404 for this handle at the recorded time; ownership and prior existence are unknown.'
                        return record
                    if code != 200:
                        record.detail = f'HTTP {code}: no usable public response. Redirects, authentication and retries were not attempted.'
                        return record
                    raw = bytearray()
                    finish_by = self.clock() + 30
                    for chunk in response.iter_content(65536):
                        raw.extend(chunk)
                        if len(raw) > 1_000_000 or self.clock() > finish_by:
                            record.detail = 'Public response exceeded size or total time limit.'
                            return record
                    record.response_sha256 = hashlib.sha256(raw).hexdigest()
                    payload = json.loads(raw)
            except requests.RequestException:
                record.detail = 'Public request failed or timed out. No authenticated fallback or automatic retry attempted.'
                return record
            except (ValueError, UnicodeError, RecursionError):
                record.detail = 'Public API returned invalid JSON; no profile information recorded.'
                return record
            finally:
                self.session.cookies.clear()
        if provider == 'GitLab':
            if not isinstance(payload, list):
                record.detail = 'Unexpected public API response structure.'
                return record
            if not payload:
                record.status = 'no_exact_result'
                record.detail = 'No exact public handle returned by the selected API; this is not proof of account absence.'
                return record
            payload = payload[0]
        key = 'login' if provider == 'GitHub' else 'username'
        if not isinstance(payload, dict) or not isinstance(payload.get(key), str):
            record.detail = 'Public response did not contain a usable username.'
            return record
        if payload[key].casefold() != handle.casefold():
            record.detail = 'Returned handle did not match the requested handle exactly; result rejected.'
            return record
        url = payload.get('html_url' if provider == 'GitHub' else 'web_url', '')
        try:
            public_url(url)
            expected_host = 'github.com' if provider == 'GitHub' else 'gitlab.com'
            if urlsplit(url).hostname != expected_host or urlsplit(url).path.strip('/').casefold() != handle:
                raise ValueError('Unexpected public profile URL')
        except (ValueError, AttributeError, TypeError):
            record.detail = 'Returned profile link was invalid or did not belong to the selected provider/handle.'
            return record
        record.status = 'exact_public_handle'
        record.returned_username, record.profile_url = payload[key], url
        # Intentionally omit email, location, keys, avatar URLs, organizations and arbitrary profile links.
        keys = ('type', 'public_repos', 'followers', 'following', 'created_at', 'updated_at') if provider == 'GitHub' else ()
        record.fields = {key: value for key in keys if type(value := payload.get(key)) in (str, int)}
        record.detail = LIMITATION
        return record

    def _save(self, path, next_allowed):
        atomic_write(path, json.dumps({'next_allowed': next_allowed}, allow_nan=False))

    def research(self, handle, providers=PROVIDERS):
        if not providers or any(p not in PROVIDERS for p in providers):
            raise ValueError('Select at least one supported public provider.')
        return [self.lookup(handle, provider) for provider in dict.fromkeys(providers)]


def record_research(case, directory, results):
    if any(result.requested_username != case.username for result in results):
        raise ValueError('Research result belongs to another case username.')
    def apply(draft):
        for result in results:
            # A cooldown/temporary failure must not erase a prior successful observation.
            if result.status == 'exact_public_handle':
                draft.public_results = [r for r in draft.public_results if r.provider != result.provider]
            elif any(r.provider == result.provider and r.status == 'exact_public_handle' for r in draft.public_results):
                draft.audit_log.append({'at': result.checked_at, 'action': 'public_lookup', 'provider': result.provider,
                                        'status': result.status, 'detail': result.detail})
                continue
            else:
                draft.public_results = [r for r in draft.public_results if r.provider != result.provider]
            draft.public_results.append(result)
            draft.audit_log.append({'at': result.checked_at, 'action': 'public_lookup', 'provider': result.provider,
                                    'status': result.status, 'request_url': result.request_url, 'detail': result.detail})
    commit_case(case, directory, apply)
