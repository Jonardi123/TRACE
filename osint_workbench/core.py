from __future__ import annotations

import ipaddress
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uid() -> str:
    return uuid.uuid4().hex[:16]


def username(value: str) -> str:
    value = value.strip().removeprefix("@").lower()
    if not re.fullmatch(r"[a-z0-9._]{1,30}", value):
        raise ValueError("Username must contain 1–30 letters, digits, periods or underscores.")
    return value


def public_url(value: str) -> str:
    """Validate external links; never retrieve them from the application."""
    value = value.strip()
    if not value or any(ord(c) < 33 for c in value) or "\\" in value:
        raise ValueError("Provide a public HTTP(S) URL without spaces or control characters.")
    try:
        p = urlsplit(value)
        host = p.hostname or ""
        port = p.port
    except ValueError as exc:
        raise ValueError("Invalid source URL.") from exc
    if p.scheme not in {"http", "https"} or not host or p.username or p.password:
        raise ValueError("Only public HTTP(S) links without credentials are accepted.")
    if port not in {None, 80, 443}:
        raise ValueError("Source links must use standard web ports.")
    if host.lower() == "localhost" or host.lower().endswith((".local", ".internal", ".localhost")):
        raise ValueError("Private/local source links are not accepted.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or not re.fullmatch(r"[A-Za-z0-9.-]+", host) or not re.search(r"[A-Za-z]", host.rsplit('.', 1)[-1]):
            raise ValueError("Provide a public hostname or global IP address.")
    else:
        if not address.is_global:
            raise ValueError("Private/local source links are not accepted.")
    return value


def timestamp(value, *, milliseconds=False) -> str | None:
    """Only timezone-aware times; never infer timezone from this computer."""
    if value is None or value == "":
        return None
    try:
        if milliseconds:
            if isinstance(value, bool):
                return None
            result = datetime.fromtimestamp(float(value) / 1000, timezone.utc)
        else:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if result.tzinfo is None:
                return None
        return result.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


@dataclass
class Evidence:
    id: str
    kind: str
    filename: str
    sha256: str
    imported_at: str
    capture_at: str | None = None
    source_url: str = ""
    notes: str = ""
    ocr_text: str = ""
    ocr_confidence: float | None = None
    warnings: list[str] = field(default_factory=list)
    original_filename: str = ""
    excluded: bool = False
    image_info: dict = field(default_factory=dict)
    ocr_at: str | None = None


@dataclass
class Message:
    sender: str
    text: str
    timestamp: str | None
    evidence_id: str
    row: int


@dataclass
class Observation:
    field: str
    value: str
    source_url: str
    observed_at: str
    evidence_id: str = ""
    recorded_at: str = field(default_factory=now)
    basis: str = "Public page observation"


@dataclass
class PublicResult:
    provider: str
    requested_username: str
    status: str
    checked_at: str
    request_url: str
    profile_url: str = ""
    returned_username: str = ""
    fields: dict = field(default_factory=dict)
    detail: str = ""
    response_sha256: str = ""


@dataclass
class InstagramReview:
    access_status: str = "Not checked"
    checked_at: str | None = None
    notes: str = ""


@dataclass
class Match:
    title: str
    url: str
    snippet: str
    retrieved_at: str
    provider: str
    exact: bool
    match_basis: str
    query: str = ""


@dataclass
class Finding:
    category: str
    title: str
    detail: str
    confidence: str
    explanation: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class Case:
    username: str
    id: str = field(default_factory=uid)
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    target_sender: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    search_log: list[dict] = field(default_factory=list)
    schema_version: int = 1
    public_results: list[PublicResult] = field(default_factory=list)
    instagram_review: InstagramReview = field(default_factory=InstagramReview)
    audit_log: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Case JSON must be an object.")
        data = dict(data)
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported case version.")
        try:
            data["username"] = username(data["username"])
            for key, typ in (("evidence", Evidence), ("messages", Message),
                             ("observations", Observation), ("matches", Match), ("public_results", PublicResult)):
                if not isinstance(data.get(key, []), list):
                    raise ValueError(f"Case {key} must be a list.")
                data[key] = [typ(**item) for item in data.get(key, [])]
            data['instagram_review'] = InstagramReview(**data.get('instagram_review', {}))
            case = cls(**data)
            validate_case(case)
            return case
        except (TypeError, KeyError, AttributeError) as exc:
            raise ValueError("Case JSON has malformed or missing fields.") from exc


def validate_case(case: Case):
    """Reject malformed persisted state before it reaches analysis or the GUI."""
    def text(value):
        if not isinstance(value, str):
            raise ValueError("Case text fields must be strings.")

    def date(value, optional=False):
        if optional and value is None:
            return
        if timestamp(value) is None:
            raise ValueError("Case timestamps must include a timezone.")

    for value in (case.id, case.target_sender):
        text(value)
    date(case.created_at)
    date(case.updated_at)
    if len(case.evidence) > 100 or len(case.messages) > 10_000:
        raise ValueError("Case exceeds evidence or message limits.")
    identifiers = set()
    for item in case.evidence:
        if not isinstance(item.id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', item.id) or item.id in identifiers:
            raise ValueError("Evidence IDs must be unique safe identifiers.")
        identifiers.add(item.id)
        if item.kind not in {'messages', 'screenshot'}:
            raise ValueError("Unsupported evidence type.")
        if not isinstance(item.filename, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9]+', item.filename):
            raise ValueError("Evidence filenames must be safe local basenames.")
        if not isinstance(item.sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', item.sha256):
            raise ValueError("Evidence hashes must be SHA-256 hex digests.")
        for value in (item.notes, item.ocr_text, item.original_filename, item.source_url):
            text(value)
        if type(item.excluded) is not bool or not isinstance(item.image_info, dict):
            raise ValueError("Malformed evidence metadata.")
        if not isinstance(item.warnings, list) or not all(isinstance(w, str) for w in item.warnings):
            raise ValueError("Evidence warnings must be strings.")
        if item.ocr_confidence is not None and (type(item.ocr_confidence) not in (int, float) or not 0 <= item.ocr_confidence <= 100):
            raise ValueError("OCR score must be between zero and 100.")
        date(item.imported_at)
        date(item.capture_at, True)
        date(item.ocr_at, True)
        if item.source_url:
            public_url(item.source_url)
    for message in case.messages:
        for value in (message.sender, message.text, message.evidence_id):
            text(value)
        if message.evidence_id not in identifiers or type(message.row) is not int or message.row < 1:
            raise ValueError("Messages must reference an existing evidence file and positive row number.")
        if message.timestamp is not None:
            normalized = timestamp(message.timestamp)
            if normalized is None:
                raise ValueError("Malformed saved message timestamp.")
            message.timestamp = normalized
    for observation in case.observations:
        for value in (observation.field, observation.value, observation.source_url, observation.evidence_id):
            text(value)
        if observation.evidence_id and observation.evidence_id not in identifiers:
            raise ValueError("Observation references unknown evidence.")
        if observation.basis not in {'Public page observation', 'Supplied evidence transcription', 'Unverified note'}:
            raise ValueError("Unknown observation basis.")
        public_url(observation.source_url)
        date(observation.observed_at)
        date(observation.recorded_at)
    for match in case.matches:
        for value in (match.title, match.snippet, match.provider, match.match_basis, match.query):
            text(value)
        if type(match.exact) is not bool:
            raise ValueError("Malformed match flag.")
        public_url(match.url)
        date(match.retrieved_at)
    if case.instagram_review.access_status not in {'Not checked', 'Public view reviewed', 'Restricted / login required', 'Unavailable'}:
        raise ValueError("Unknown Instagram access status.")
    text(case.instagram_review.notes)
    date(case.instagram_review.checked_at, True)
    if case.instagram_review.access_status != 'Not checked' and case.instagram_review.checked_at is None:
        raise ValueError('A recorded Instagram access review requires a timestamp.')
    for result in case.public_results:
        for value in (result.provider, result.requested_username, result.status, result.returned_username, result.detail, result.response_sha256):
            text(value)
        public_url(result.request_url)
        if result.profile_url:
            public_url(result.profile_url)
        date(result.checked_at)
        if result.provider not in {'GitHub', 'GitLab'} or result.requested_username != case.username:
            raise ValueError('Public results must use a supported provider and this case username.')
        if result.status not in {'exact_public_handle', 'unsupported_handle', 'unavailable', 'rate_limited', 'no_exact_result'}:
            raise ValueError('Unknown public result status.')
        if result.response_sha256 and not re.fullmatch(r'[a-f0-9]{64}', result.response_sha256):
            raise ValueError('Malformed public response digest.')
        if not isinstance(result.fields, dict) or not all(isinstance(k, str) and type(v) in (str, int) for k, v in result.fields.items()):
            raise ValueError("Public result fields must contain only text or integer observations.")
        allowed = {'type', 'public_repos', 'followers', 'following', 'created_at', 'updated_at'} if result.provider == 'GitHub' else set()
        if not set(result.fields).issubset(allowed):
            raise ValueError('Public result contains fields TRACE does not collect.')
        if result.status == 'exact_public_handle':
            expected = 'github.com' if result.provider == 'GitHub' else 'gitlab.com'
            url = urlsplit(result.profile_url)
            if (result.returned_username.casefold() != case.username or url.hostname != expected
                    or url.path.strip('/').casefold() != case.username):
                raise ValueError('Exact public result must contain the expected handle and provider profile URL.')
        elif result.fields or result.profile_url or result.returned_username:
            raise ValueError('Unavailable public results cannot claim retrieved profile information.')
    for log in (case.search_log, case.audit_log):
        if not isinstance(log, list) or not all(isinstance(item, dict) for item in log):
            raise ValueError("Case logs must contain objects.")
