"""Only an official fixed-endpoint API or user-opened browser search; no scraping."""
import hashlib
import html
import json
import math
import os
import re
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import requests
from filelock import FileLock

from .core import Match, now, public_url, username
from .paths import rate_state_directory

API_URL = "https://api.search.brave.com/res/v1/web/search"


class SearchError(ValueError):
    pass


def browser_search_url(handle: str, engine="DuckDuckGo") -> str:
    query = quote(f'"{username(handle)}"', safe="")
    base = {"DuckDuckGo": "https://duckduckgo.com/?q=", "Brave": "https://search.brave.com/search?q="}
    return base[engine] + query


def clean_text(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", value))


def exact_match(handle: str, title: str, url: str, snippet: str) -> tuple[bool, str]:
    handle = username(handle)
    # Username punctuation belongs to the token, so alice is not alice_1 or alice.name.
    pattern = re.compile(r"(?<![a-z0-9._])" + re.escape(handle) + r"(?![a-z0-9._])", re.I)
    path = unquote(urlsplit(url).path)
    if pattern.search(path):
        return True, "Exact token in URL path; ownership unverified"
    if pattern.search(clean_text(title)) or pattern.search(clean_text(snippet)):
        return True, "Exact token in indexed title/snippet; may only be a mention"
    return False, "No exact username token found"


def make_match(handle, title, url, snippet="", provider="Manual indexed result", query="") -> Match:
    url = public_url(url)
    title, snippet = clean_text(title), clean_text(snippet)
    exact, basis = exact_match(handle, title, url, snippet)
    if not exact:
        raise ValueError("Result contains no exact username token in its URL path, title or snippet.")
    return Match(title, url, snippet, now(), provider, True, basis, query)


def retry_delay(value: str | None, clock=time.time) -> float:
    if not value:
        return 60
    try:
        seconds = float(value)
        return max(60, seconds) if math.isfinite(seconds) else 60
    except ValueError:
        try:
            return max(60, parsedate_to_datetime(value).timestamp() - clock())
        except (TypeError, ValueError, OverflowError):
            return 60


class BraveSearch:
    def __init__(self, key=None, state_dir=None, interval=5, session=None, clock=time.time):
        self.key = key if key is not None else os.environ.get("BRAVE_SEARCH_API_KEY", "")
        if not self.key:
            raise SearchError("Set BRAVE_SEARCH_API_KEY to use the official API, or use browser search.")
        self.interval = max(5, float(interval))
        self.clock = clock
        base = Path(state_dir) if state_dir else rate_state_directory()
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Share rate state between processes/cases using the same credential, without storing it.
        identifier = hashlib.sha256(self.key.encode()).hexdigest()[:24]
        self.state_file = base / f"search-{identifier}.json"
        self.lock_file = base / f"search-{identifier}.lock"
        self.session = session or requests.Session()
        self.session.trust_env = False  # Do not accidentally send credentials via environment proxies.
        self.session.headers.clear()
        self.session.cookies.clear()

    def search(self, handle: str) -> tuple[list[Match], dict]:
        query = f'"{username(handle)}"'
        with FileLock(self.lock_file, timeout=30, mode=0o600):
            try:
                state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {}
                wait = float(state.get("next_allowed", 0)) - self.clock()
                if not math.isfinite(wait):
                    raise ValueError('Invalid rate state')
            except (AttributeError, ValueError, TypeError, OSError) as exc:
                raise SearchError("Rate-limit state is unreadable; inspect it before making more requests.") from exc
            if wait > 0:
                raise SearchError(f"Rate limit: wait {int(wait) + 1} seconds before another API request.")
            self._save_state(self.clock() + self.interval)
            try:
                with self.session.get(API_URL, params={"q": query, "count": 20, "safesearch": "moderate"},
                        headers={"X-Subscription-Token": self.key, "Accept": "application/json",
                                 "User-Agent": "TRACE/0.2"},
                        timeout=(5, 20), allow_redirects=False, stream=True) as response:
                    # Respect Retry-After on any response, including overload responses.
                    if response.headers.get("Retry-After") or response.status_code == 429:
                        self._save_state(self.clock() + retry_delay(response.headers.get("Retry-After"), self.clock))
                    if response.status_code == 429:
                        raise SearchError("Provider rate limit reached. Retry-After cooldown saved; no automatic retries.")
                    if response.status_code in {401, 403}:
                        raise SearchError("Provider denied access. Check your API subscription and terms; no fallback attempted.")
                    if response.status_code != 200:
                        raise SearchError(f"Provider returned HTTP {response.status_code}; no retry or redirect attempted.")
                    chunks = []
                    total = 0
                    deadline = self.clock() + 30
                    for chunk in response.iter_content(65536):
                        total += len(chunk)
                        if total > 2_000_000 or self.clock() > deadline:
                            raise SearchError("Search response exceeded size or total time limit.")
                        chunks.append(chunk)
                    payload = json.loads(b"".join(chunks))
            except requests.RequestException:
                raise SearchError("Search request failed or timed out. No automatic retry attempted.") from None
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise SearchError("Provider returned invalid JSON.") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("web", {}), dict):
            raise SearchError("Provider returned an unexpected result structure.")
        rows = payload.get("web", {}).get("results", [])
        if not isinstance(rows, list):
            raise SearchError("Provider results must be a list.")
        matches, seen = [], set()
        rejected = 0
        for row in rows[:20]:
            try:
                if not isinstance(row, dict) or not all(isinstance(row.get(k, ""), str) for k in ("title", "url", "description")):
                    raise ValueError("Invalid result")
                match = make_match(handle, row.get("title", ""), row.get("url", ""), row.get("description", ""),
                                   "Brave Search API", query)
                if match.url not in seen:
                    matches.append(match)
                    seen.add(match.url)
            except ValueError:
                rejected += 1
        log = {"query": query, "provider": "Brave Search API", "retrieved_at": now(),
               "returned": min(len(rows), 20), "accepted": len(matches), "rejected": rejected,
               "limitation": "One index page only. No target websites fetched; snippets may be stale or mentions. "
                             "No results does not establish account absence."}
        return matches, log

    def _save_state(self, next_allowed):
        from .storage import atomic_write
        atomic_write(self.state_file, json.dumps({"next_allowed": next_allowed}))
