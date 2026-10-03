from html import escape
from pathlib import Path

from .analysis import analyze
from .core import Case, now, public_url
from .storage import atomic_write, verify_evidence
from .workflow import checklist, profile_url

STYLE = """
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0b1220;color:#e6edf7;font:15px/1.65 system-ui,sans-serif}
main{max-width:1150px;margin:auto;padding:48px 28px}header{border-bottom:3px solid #247e89;margin-bottom:28px}
h1{font-size:36px;letter-spacing:-1px;margin:8px 0}h2{margin-top:32px}h3{margin:4px 0 10px}p{margin:8px 0}
.kicker{color:#59d3c3;font-weight:700;letter-spacing:2px}.card{padding:20px;background:#152239;border:1px solid #304157;border-radius:12px;margin:14px 0}
.verified{border-left:5px solid #188473}.possible{border-left:5px solid #bc821b}.unsupported{border-left:5px solid #758399}
.badge{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#a6b5ca}small{color:#a6b5ca}
a{color:#7be2d4;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#101b2d;padding:12px}
table{border-collapse:collapse;width:100%;background:#152239}th,td{padding:12px;border:1px solid #304157;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#24364e}.hash{font:12px monospace;word-break:break-all} @media print{:root{color-scheme:light}body{background:white;color:#17243b}main{padding:0}.card,table,th,pre{background:white;color:#17243b}.card{break-inside:avoid}a,small,.badge{color:#17243b}}
"""


def e(value):
    return escape(str(value), quote=True)


def link(url, label=None):
    try:
        safe = public_url(url)
    except ValueError:
        return e(label or url) + " (invalid link omitted)"
    return f'<a href="{e(safe)}" rel="noreferrer noopener">{e(label or safe)}</a>'


def build_report(case: Case, directory: Path, *, include_text=False) -> str:
    integrity = dict(verify_evidence(case, directory))
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; img-src &#39;none&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">',
        f'<title>TRACE evidence report · @{e(case.username)}</title><style>{STYLE}</style></head><body><main>',
        f'<header><div class="kicker">TRACE / LOCAL EVIDENCE</div><h1>@{e(case.username)}</h1>',
        f'<p>Case {e(case.id)} · Created {e(case.created_at)} · Report generated {e(now())}</p></header>',
        '<div class="card"><h3>How to read this report</h3><p><b>Verified</b> means a directly computed fact about the supplied case. '
        'It does not authenticate an export, screenshot or investigator statement. <b>Possible</b> means a match, '
        'observation or heuristic requiring corroboration. <b>Unsupported</b> means available evidence does not justify the claim.</p>'
        '<p>Confidence labels describe support for the stated observation, not the probability of bot activity. '
        'No identity attribution is performed. All system times use UTC; missing capture times remain unknown.</p></div>',
        '<h2>Findings</h2>']
    problems = [(identifier, state) for identifier, state in integrity.items() if state != 'intact']
    if problems:
        parts.append('<div class="card possible"><h3>Evidence integrity warning</h3><p>' +
                     e('; '.join(f'{identifier}: {state}' for identifier, state in problems)) +
                     '</p><p>Findings use the saved parsed case data. Inspect these discrepancies before relying on the report.</p></div>')
    for finding in analyze(case):
        references = ", ".join(f'<a href="#evidence-{e(i)}">{e(i)}</a>' for i in finding.evidence_ids)
        parts.append(f'<article class="card {e(finding.category)}"><div class="badge">{e(finding.category)} · '
            f'Confidence: {e(finding.confidence)}</div><h3>{e(finding.title)}</h3><p>{e(finding.detail)}</p>'
            f'<p><small>{e(finding.explanation)}</small></p><p><small>Evidence: {references or "No file citation"}</small></p></article>')
    parts.append('<h2>Instagram investigation workflow</h2><div class="card">'
                 + f'<p>Public profile: {link(profile_url(case))}</p><p>Investigator-reported access status: <b>{e(case.instagram_review.access_status)}</b>'
                 + f' · Review time: {e(case.instagram_review.checked_at or "unknown")}</p><p>{e(case.instagram_review.notes)}</p>'
                 + '<p>TRACE does not retrieve Instagram content or verify access automatically. Restricted/login-gated content remains unavailable.</p>'
                 + '<table><tr><th>Public field</th><th>Documentation status</th></tr>'
                 + ''.join(f'<tr><td>{e(field)}</td><td>{e(status)}</td></tr>' for field, status in checklist(case))
                 + '</table></div>')
    parts.append('<h2>Public profile observations</h2><p>Manually entered observations; no Instagram requests were made.</p>')
    for observation in case.observations:
        parts.append(f'<div class="card"><h3>{e(observation.field)}</h3><p>{e(observation.value)}</p>'
            f'<p>{link(observation.source_url)} · Observed {e(observation.observed_at)} · Recorded {e(observation.recorded_at)}</p>'
            f'<p>Basis: {e(observation.basis)} · Supporting file: {e(observation.evidence_id or "none attached")}</p></div>')
    if not case.observations:
        parts.append('<p>No public observations recorded.</p>')
    parts.append('<h2>Exact username search results</h2><p>All results are possible matches. '
                 'An exact token may be a mention; account ownership is unverified. Search indexing may be incomplete.</p>')
    for match in case.matches:
        parts.append(f'<div class="card possible"><h3>{link(match.url, match.title or match.url)}</h3><p>{e(match.snippet)}</p>'
            f'<p>{e(match.match_basis)}</p><small>{e(match.provider)} · Recorded {e(match.retrieved_at)} · '
            f'Query {e(match.query or "manually supplied")}</small></div>')
    if not case.matches:
        parts.append('<p>No exact indexed results recorded. This does not establish that no matching accounts exist.</p>')
    for log in case.search_log:
        parts.append('<div class="card"><h3>Search audit</h3><pre>' + e("\n".join(f"{k}: {v}" for k, v in log.items())) + '</pre></div>')
    parts.append('<h2>Public API username research</h2><p>Direct exact-handle lookups are separate from indexed web searches. '
                 'An observed public handle is not evidence of common ownership or real-world identity.</p>')
    if not case.public_results:
        parts.append('<p>No direct public profile lookup recorded.</p>')
    for result in case.public_results:
        parts.append(f'<div class="card possible"><h3>{e(result.provider)} · {e(result.status)}</h3>'
            f'<p>Requested handle: {e(result.requested_username)} · Returned handle: {e(result.returned_username or "none recorded")}</p>'
            f'<p>Checked {e(result.checked_at)} · API source: {link(result.request_url)}</p>'
            f'<p>{link(result.profile_url) if result.profile_url else "No accessible public profile link recorded"}</p>'
            f'<p>{e(result.detail)}</p><pre>{e(chr(10).join(f"{k}: {v}" for k,v in result.fields.items()) or "No public fields retrieved")}</pre>'
            f'<p class="hash">Response SHA-256: {e(result.response_sha256 or "unavailable")}</p>'
            '<small>Raw API bodies are not retained; only the listed fields and response digest are stored.</small></div>')
    parts.append('<h2>Evidence inventory and integrity</h2><p>Hashes establish byte identity since import, not authenticity. '
                 'Copies are stored separately; this HTML report embeds no original files or remote assets.</p>')
    for item in case.evidence:
        state = integrity.get(item.id, "unchecked")
        parts.append(f'<article class="card" id="evidence-{e(item.id)}"><h3>{e(item.kind)} · {e(item.id)}</h3>'
            f'<p>Stored file: {e(item.filename)} · Current integrity: <b>{e(state)}</b></p>'
            f'<p>Original filename: {e(item.original_filename or "not recorded by older version")} · '
            f'Analysis status: {"excluded (original retained)" if item.excluded else "active"}</p>'
            f'<p>Imported {e(item.imported_at)} · Capture time {e(item.capture_at or "unknown")}</p>'
            f'<p class="hash">SHA-256 {e(item.sha256)}</p><p>{link(item.source_url) if item.source_url else "No public source URL supplied"}</p>'
            f'<p>{e(item.notes)}</p>')
        for warning in item.warnings:
            parts.append(f'<p><small>{e(warning)}</small></p>')
        if item.kind == "screenshot":
            parts.append(f'<p>Image information: {e(item.image_info or "not recorded")} · Last OCR: {e(item.ocr_at or "not recorded")}</p>')
            parts.append(f'<p>Mean OCR word confidence: {e(item.ocr_confidence if item.ocr_confidence is not None else "unavailable")}. '
                         'This is an engine score, not factual confidence. Review against the screenshot.</p>')
            if include_text and item.ocr_text:
                parts.append(f'<details><summary>OCR transcription (unverified)</summary><pre>{e(item.ocr_text)}</pre></details>')
        parts.append('</article>')
    if include_text:
        parts.append('<h2>Supplied message text</h2><p>Contains all imported sender labels and message text; '
                     'attribution and content have not been independently authenticated.</p><table><tr>'
                     '<th>Evidence / row</th><th>Sender</th><th>UTC time</th><th>Text</th></tr>')
        for message in case.messages:
            parts.append(f'<tr><td>{e(message.evidence_id)} / {e(message.row)}</td><td>{e(message.sender or "unattributed")}</td>'
                         f'<td>{e(message.timestamp or "unknown")}</td><td>{e(message.text)}</td></tr>')
        parts.append('</table>')
    else:
        parts.append('<p>Raw message bodies and OCR transcriptions were omitted from this report. '
                     'Profile observations, notes and indexed snippets are still included.</p>')
    parts.append('<h2>Case activity log</h2>')
    if case.audit_log:
        parts.append('<div class="card"><pre>' + e('\n'.join(str(event) for event in case.audit_log)) + '</pre></div>')
    else:
        parts.append('<p>No activity log recorded by this case version.</p>')
    parts.append('<h2>Limits and methodology</h2><div class="card"><p>Only manually supplied public observations, '
        'voluntarily supplied evidence, and recorded public-index results were considered. No authentication, privacy bypass, '
        'hidden-contact extraction, leaked databases or attempts to identify anonymous individuals were used.</p>'
        '<p>Heuristic thresholds: at least eight selected text messages; repetition ≥40% with an identical group ≥3; '
        'timing within each evidence file: at least eight valid times, all gaps positive, mean gap 5–3600 seconds '
        'and coefficient of variation ≤0.10; bursts ≥10 messages in an inclusive 60-second window. '
        'These thresholds are not empirically calibrated. Missing data, edited exports, timestamp rounding, selection bias, '
        'multiple conversations within one export and overlaps can affect findings. Case metadata is editable JSON, '
        'not a signed chain-of-custody record; stored hashes only check evidence copies against the recorded digest.</p>'
        '<p>Version 0.2.0 · TRACE · Local report · No JavaScript, remote images, tracking or analytics.</p></div></main></body></html>')
    return "\n".join(parts)


def export_report(case: Case, directory: Path, destination: Path, *, include_text=False):
    destination = Path(destination)
    if destination.suffix.lower() != '.html':
        raise ValueError('Report destination must end in .html.')
    if destination.resolve().is_relative_to((Path(directory) / 'evidence').resolve()):
        raise ValueError('Report destination cannot overwrite the evidence directory.')
    atomic_write(Path(destination), build_report(case, directory, include_text=include_text))
