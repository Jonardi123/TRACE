# TRACE 0.2.3 validation

Validated on 3 October 2026 on Linux x86_64 using Python 3.13.16, Tk 9.0.4, Pillow 12.3.0 and Tesseract 5.3.0. A dedicated Kali VM was unavailable; the installation guide lists Kali's apt/venv dependencies.

**Final automated result: 125 passed, zero failed, zero skipped.** The original baseline had 81 passing tests; 44 additional checks now exercise public research, workflow state, exclusion, retry/rollback, archive portability, case validation, header-target protection and complete tab actions. The machine-readable result is [TEST_RESULTS.xml](TEST_RESULTS.xml).

| Feature | Verification actually performed |
| --- | --- |
| Application install | Editable version 0.2 installed; `trace-osint` and legacy entry point available; `doctor` checked local modules/Tesseract; wheel build succeeded |
| GUI | Real Tk windows launched; all four tabs selected; profile review/entry, background imports, screenshot window, OCR retry, annotation, exclusion/restoration, research result display, sender analysis, HTML/ZIP export and worker-error recovery exercised; 1000×760 controls remained mapped/scrollable |
| Standalone launch | `trace-osint gui --case examples/demo-case` launched the application with the legacy synthetic case; no network action on startup |
| Public handle research | Unit tests validate exactness, source URLs, field whitelist, auth/proxy omission, quota headers, cooldown across clients, unsupported handles and honest failures; one live unauthenticated probe per provider performed as described below |
| Instagram workflow | Restricted access preserved without fabricated profile fields; explicit timestamps required; transcript evidence and unverified-note classification checked; no Instagram request performed |
| Evidence | Original bytes/hash, duplicate rejection, row/size limits, annotation rollback, exclusion effects and saved-case compatibility checked |
| Screenshots | Actual Tesseract recognized the integration fixture and the included synthetic screenshot; preview checked digest and displayed a real local image; retry failure preserved prior OCR; changed bytes blocked reprocessing |
| Reporting | Escaping/CSP, text omission, timestamps, categories, integrity warning, workflow and public result sections checked; dark TRACE report inspected in a browser |
| Portable bundle | Manifest/originals/case/report produced; generated ZIP extracted and loaded again; changed evidence refused replacement of an existing bundle |
| Behavior heuristics | Six generated message scenarios imported/saved/reloaded/analyzed; expected signals verified, including a regular human-routine example; regression for repeated pairs without a triggered signal |
| Static checks | Python compilation and Ruff `F` checks passed |

## Native packaging follow-up

The 0.2.3 local suite includes seven extra state-path and cross-process lock checks. Linux-only imports were replaced by filelock native process locks, Windows uses a user-writable state directory, and frozen GUI/CLI smoke checks are configured before installer assembly. Historical baseline checks remain covered. Parameter IDs in TEST_RESULTS.xml are shortened with a SHA-256 suffix when very long; captured diagnostics and host attributes are omitted for publication. The GitHub release workflow builds/tests each native target and publishes executable validation records only after success; installer availability is established by the actual release assets, not this configuration.

## Live public API probe

At 2026-10-03T18:56:42+00:00, the GitHub public API returned an exact public handle for `python`. At 2026-10-03T18:56:43+00:00, GitLab returned no exact public result for the same handle. These were transport/exact-handle checks on a public handle, not an Instagram investigation. The projected results, request URLs and response digests are recorded in `LIVE_API_SMOKE_TEST.json`. No common ownership or personal identity is asserted; no-results does not prove account absence.

No live Brave subscription was used. Its existing API tests remain mocked and require no credentials. No Instagram account was retrieved or scraped. Synthetic and live transport checks are separate artifacts; live results were not inserted into a synthetic Instagram case.

## Environment details and reproducibility

This host's default Python lacks Tk and system Tesseract. Tests used an isolated Python/Tk runtime and official Debian OCR packages extracted into the local test directory, without a system install. A test-only wrapper suppressed host libcurl linker warnings during the engine's `--version`; actual Tesseract handled recognition. That wrapper is not part of TRACE and is unnecessary with Kali's packaged engine.

To repeat the full suite on Kali:

```bash
sudo apt install -y python3-venv python3-tk tesseract-ocr xvfb xauth fonts-dejavu-core
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
xvfb-run -a python -m pytest -q --junitxml=trace-tests.xml
```

Limits remain explicit: manual Instagram review; narrow public-provider coverage; no calibrated bot classifier; no source/screenshot authentication; no OCR sender/time inference; unencrypted and unsigned case metadata; one writer per case. See `BOT_ANALYSIS_VALIDATION.md` for the six scenario outcomes and interpretation.
