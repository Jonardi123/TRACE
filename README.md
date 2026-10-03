# TRACE 0.2.2

TRACE is a local Python investigation application for public account observations and evidence you are authorized to examine. This release extends the existing OSINT Workbench rather than replacing it. Existing version 0.1 cases load with defaults for new fields; the Python package and `osint-workbench` command remain compatible aliases.

The four desktop tabs are **Instagram**, **Evidence**, **Username research**, and **Analysis & report**. They share the same functions as the CLI. The interface and HTML reports use a dark TRACE theme.

## Native downloads

Download Windows setup EXE/portable ZIP, macOS PKG/app ZIP, Linux DEB/tar.gz, or source from [GitHub Releases](https://github.com/Jonardi123/TRACE/releases). See [INSTALLERS.md](INSTALLERS.md) for architecture selection, signing status, optional OCR, and native build verification. A release is published only after native builds and executable checks pass.

## Install on Kali Linux

Use Python 3.11+ in a virtual environment. Do not install pip packages into Kali's system Python.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk tesseract-ocr fonts-dejavu-core
unzip TRACE-0.2.2-source.zip
cd trace
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
trace-osint doctor
trace-osint
```

If you are using the source folder directly, change into that folder instead of extracting the ZIP. `python -m osint_workbench` and `osint-workbench` launch the same application. To open a saved case immediately:

```bash
trace-osint gui --case ./examples/trace-demo-case
```

Python dependencies are Pillow, pytesseract, Requests and filelock, all open source. Tkinter/Tk is the desktop toolkit. Tesseract is the local OCR engine. No AI model, cloud OCR or telemetry is used. A graphical X display is required for the GUI; CLI operations work headlessly. OCR is optional: screenshots import with hashes and warnings when the engine is unavailable.

`requirements-tested.txt` records exact verified Python dependency versions, including test dependencies. In a fresh venv, you can reproduce them with:

```bash
python -m pip install -r requirements-tested.txt
python -m pip install --no-deps -e .
```

`doctor` reports installed modules and the Tesseract executable path without searching the web or exposing credentials. See `VALIDATION.md` and `AUDIT.md` for actual environment checks and remaining limits.

## Workflow

### 1. Instagram

Enter a username, create a case folder, or open an existing case. The case username stays fixed. If you edit the header to another username, case actions stop until you create the appropriate case or restore the current handle, preventing research from being assigned to the wrong case.

**Open public profile** launches your browser. TRACE does not request Instagram pages or APIs, authenticate, scrape, follow private accounts or bypass access restrictions. If a browser cannot launch, the app reports that rather than claiming the page was retrieved.

Record an investigator-supplied access review: **Not checked**, **Public view reviewed**, **Restricted / login required**, or **Unavailable**. A completed review requires an explicit timezone-aware observation time. A restricted view does not cause the app to populate missing profile values.

Record public display name, biography, displayed counts, public links, visibility or public activity notes with a source URL and observation time. Counts remain the text you observed, including displayed abbreviations. Missing fields remain **not recorded**, never zero or invented.

Choose the observation basis: **Public page observation**, **Supplied evidence transcription**, or **Unverified note**. A transcription requires an active evidence ID. Unverified notes are classified as unsupported and do not complete the profile checklist. Supporting evidence that is excluded is identified explicitly. All entered account statements remain investigator-supplied, not automatically authenticated facts.

### 2. Evidence

Import screenshots or voluntarily supplied message exports. Add a public source if applicable, capture time if known, and context/permission notes. TRACE preserves original bytes in `evidence/`, stores SHA-256 and import time, and records the original basename without saving your source directory path.

Select an evidence row to review provenance, parsing warnings, image information and OCR. Use **View screenshot** to display a local, scaled preview after checking the stored bytes against the recorded digest. No screenshot is uploaded. Use **Rerun OCR** after installing Tesseract or to repeat extraction. A failed OCR retry preserves the last transcription, reports the failure and logs the attempt. A changed original blocks preview/OCR until its integrity problem is resolved.

**Save annotations** updates notes, public source and capture time while preserving the file, import timestamp and digest. **Exclude / restore** changes whether a file contributes to behavior analysis; it never deletes originals or imported records. Existing profile statements supported by excluded evidence are flagged as unsupported. Changes, exclusion and OCR attempts are recorded in the case activity log.

Imports and annotations commit to memory only after the atomic case save succeeds. Failed imports remove the uncommitted copy and leave the prior case state intact. New files use mode 600 and new case/evidence folders use mode 700; existing folder permissions are not changed.

### 3. Username research

Two distinct research methods are available:

- **Direct public profile APIs, no key required:** select GitHub and/or GitLab, then research the case's exact handle. TRACE makes one unauthenticated request per selected official endpoint. It stores only the exact handle, canonical profile link, selected public statistics/type/timestamps where returned, response digest and request timestamp. It discards contact/location fields, arbitrary profile links, avatar URLs and raw API bodies. A profile with a shared username remains an **unlinked possible match**; no Instagram ownership or personal identity is inferred.
- **Public indexed web search:** open a quoted browser search and manually add indexed results, or use the optional official Brave Search API. The existing exact-token filter is retained. Matches in a URL path differ from mentions in an indexed title/snippet. Results are not assumed to share an owner.

Direct lookup outcomes are explicit: `exact_public_handle`, `no_exact_result`, `unsupported_handle`, `unavailable`, or `rate_limited`. Unsupported GitHub handle punctuation causes no request. HTTP denials, redirects, malformed responses, timeouts and quota failures do not become findings of account absence. A temporary recheck failure retains a prior successful observation with its original timestamp and records the failed attempt in the activity log.

Each public provider has a persistent, process-shared local cooldown of at least 60 seconds. Provider Retry-After and rate-reset headers can extend it. Calls are serial; there are no automatic retries, auth fallbacks, proxy rotation or protection bypasses. Other clients can share the same public IP quota, so provider headers and denials take precedence over the local pacing. Public research is narrow provider coverage, not a search of all websites.

No network request occurs simply from opening TRACE, loading a case, importing evidence, analyzing messages or viewing a report. A public research action discloses the case handle to the selected providers; a browser/API search discloses it to the selected search engine. Follow the providers' current terms and permitted uses.

Official sources: [GitHub public user endpoint](https://docs.github.com/en/rest/users/users), [GitHub API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api), [GitLab Users API](https://docs.gitlab.com/api/users/), [Brave Web Search API](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started), [DuckDuckGo exact-query syntax](https://duckduckgo.com/duckduckgo-help-pages/results/syntax).

#### Optional Brave API

Automatic indexed web search still requires your own Brave subscription key. Choose a plan permitting your intended result retention and follow its current usage/storage terms; the application does not grant those permissions. Set the key before launching without placing its value in shell history:

```bash
read -rsp 'Brave API key: ' BRAVE_SEARCH_API_KEY
printf '\n'
export BRAVE_SEARCH_API_KEY
trace-osint
unset BRAVE_SEARCH_API_KEY
```

TRACE does not print or persist the key. One click requests one page of up to 20 results, with a minimum five-second interval and persisted Retry-After handling. The key fingerprint determines shared rate state, not the credential itself. State for both research adapters remains under `$XDG_STATE_HOME/osint-workbench/`, defaulting to `~/.local/state/osint-workbench/` on POSIX and `%LOCALAPPDATA%/osint-workbench/` on Windows. Native process locks coordinate cooldowns on Windows, macOS and Linux. Custom endpoints, arbitrary crawlers and authenticated platform access are not supported.

### 4. Analysis & report

Select the export's exact sender label before analyzing behavior. Linking that label to the account is your supplied attribution. OCR or unlabeled text is never automatically assigned to the account.

Findings separate:

- **Verified:** direct measurements of the saved case, such as file/message counts, repetition or timing. This does not authenticate a source or establish profile claims as true.
- **Possible:** unlinked public handle candidates, investigator observations and cautious behavior signals requiring corroboration.
- **Unsupported:** unverified notes, excluded-source statements, insufficient data, identity linkage and bot certainty.

Confidence explains support for the stated observation, not a numerical chance of automation. Copying, scheduled replies, human routines, timestamp rounding, partial exports and multiple conversations can produce misleading signals. See `BOT_ANALYSIS_VALIDATION.md` and the supplied synthetic fixtures for tested examples, including a human-routine scenario that triggers regular timing.

Export a self-contained HTML report with TRACE branding, provenance, timestamps, source links, integrity warnings, API lookup outcomes, the Instagram review/checklist, confidence explanations, thresholds and activity logs. Raw message bodies and OCR transcripts are omitted by default. The opt-in checkbox includes **all imported senders' messages**, including retained excluded records; observations, notes and indexed snippets are always included. Reports contain no scripts, remote images, analytics or external styles. Text/URLs are escaped and protected by a Content Security Policy. Source links navigate only when clicked. Print styling switches to a light page.

**Export full case ZIP** is a separate local archival operation. It includes `case.json`, all original evidence (including excluded files and supplied conversation records), `report.html` and a hash manifest. It verifies originals first and refuses to replace a bundle with inconsistent evidence. No bundle is uploaded. Extract sensitive case bundles into a protected folder, using an appropriate umask; ZIP and case JSON are plaintext, not encrypted or cryptographically signed.

## Supported formats and limits

Instagram-shaped JSON: an object with `messages`, containing `sender_name`, `content` and `timestamp_ms`. Import the voluntarily supplied `message_1.json` itself, not an entire account archive. Attachments/reactions/non-text records are skipped with counts; no attachment URL or archive path is followed.

Generic JSON:

```json
[
  {"sender": "Chosen sender", "timestamp": "2026-01-01T12:00:00+02:00", "text": "A supplied message"}
]
```

CSV requires `sender,text`; `timestamp` is optional:

```csv
sender,timestamp,text
Chosen sender,2026-01-01T12:00:00Z,A supplied message
```

UTF-8 TXT stores each nonempty line as an unattributed record with no time. Invalid and timezone-naive timestamps remain unknown and do not enter timing analysis. Saved cases validate field types, references, digests and timezone-aware timestamps before loading. Export text is preserved as supplied, including original encoding artifacts; corrections should be separately documented.

Screenshots: PNG/JPEG/WebP/TIFF/BMP, up to 20 MB and 20 million pixels. Only the first frame/page is examined. Tesseract English OCR has a 30-second recognition timeout. Image information records size, format and frame count; TRACE does not extract hidden contact details or location metadata. Engine word confidence is not screenshot-authenticity or factual confidence.

Limits: 5 MB per text export; 10,000 text records per case; 100 evidence files; 100 MB for loaded case JSON. Duplicate original files are rejected by SHA-256. Use one app/CLI writer per case at a time. Back up the entire folder; editable metadata and hashes are not a signed forensic chain-of-custody system.

## CLI examples

```bash
trace-osint demo ./cases/demo
trace-osint gui --case ./cases/demo
trace-osint new example_handle ./cases/exercise
trace-osint import ./cases/exercise ./examples/instagram-export.json --notes 'Voluntarily supplied sample'
trace-osint analyze ./cases/exercise --sender 'Demo sender'
trace-osint research ./cases/exercise --provider GitHub --provider GitLab
trace-osint review ./cases/exercise --status 'Restricted / login required' --checked-at '2026-01-01T12:00:00Z'
trace-osint evidence ./cases/exercise EVIDENCE_ID --exclude --notes 'Retained but excluded from behavior analysis'
trace-osint evidence ./cases/exercise EVIDENCE_ID --restore
trace-osint ocr ./cases/exercise SCREENSHOT_EVIDENCE_ID
trace-osint report ./cases/exercise ./cases/exercise/report.html
trace-osint bundle ./cases/exercise ./cases/exercise/full-case.zip
```

The `demo` command is entirely synthetic and performs no searches. `examples/trace-demo-case` additionally contains a supplied synthetic screenshot with tested OCR. `examples/demo-case` is retained as a legacy-reader example. `examples/synthetic-messages/` contains six distinct generated behavior scenarios. The separate `LIVE_API_SMOKE_TEST.json` describes an actual public API transport check; it is not attached to a synthetic Instagram case or presented as an Instagram investigation.

## Architecture retained and extended

| Module | Responsibility |
| --- | --- |
| `core.py` | Case/evidence models, validation, public results and Instagram review state |
| `paths.py` | Compatible user-writable rate-state locations across platforms |
| `storage.py` | Atomic saves, transaction copies, bounded file reads and integrity checks |
| `evidence.py` | Message parsing, screenshots, local OCR, annotation and exclusion |
| `search.py` | Existing public-index browser/Brave search and exact-token filtering |
| `research.py` | New fixed official GitHub/GitLab public profile API lookups and pacing |
| `workflow.py` | Investigator-supplied Instagram access reviews, observations and checklist |
| `analysis.py` | Existing sender-isolated heuristics with exclusion and no-signal correction |
| `report.py` | Escaped, self-contained TRACE HTML reporting |
| `bundle.py` | Local portable archive with original evidence and manifest |
| `gui.py` | Four-tab Tk interface and background OCR/network work |
| `__main__.py` | GUI/CLI commands and dependency checks |

## Tests and remaining limitations

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
# For a headless Kali host:
sudo apt install -y xvfb xauth
xvfb-run -a python -m pytest -q
```

Network unit tests are mocked. GUI tests exercise real Tk widgets, local imports, preview, OCR retry, research result display, sender selection, HTML and ZIP exports, and background-error recovery. An OCR integration test uses actual Tesseract when installed. GUI and OCR tests skip if their system dependencies/display are absent; see `VALIDATION.md` for the complete, non-skipped run actually performed.

Remaining limitations: no automatic Instagram access; incomplete GitHub/GitLab coverage; optional Brave needs a subscription; no screenshot/source authentication; no calibrated bot classifier; no automatic attribution of OCR/plain text; editable, unencrypted local metadata; single writer per case; multiple conversations within one file can distort timing. A Linux desktop was tested, but a dedicated Kali VM was unavailable. TRACE never retrieves hidden contact details, leaked records or private messages and never tries to identify an anonymous person.

License: MIT. Third-party libraries and services retain their own licenses and terms.
