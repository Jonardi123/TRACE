"""Explainable heuristics, not a trained classifier or probability estimate."""
from collections import Counter
from datetime import datetime
import re
import statistics

from .core import Case, Finding


def analyze(case: Case) -> list[Finding]:
    findings = []
    all_ids = [e.id for e in case.evidence]
    excluded = {e.id for e in case.evidence if e.excluded}
    findings.append(Finding("verified", "Evidence inventory",
        f"{len(case.evidence)} imported files; {len(case.messages)} text records; "
        f"{len(case.observations)} saved profile observations/notes; {len(excluded)} files excluded from behavior analysis.", "high",
        "These counts are verified within the case. They do not authenticate supplied evidence.", all_ids))
    for observation in case.observations:
        unsupported = observation.basis == 'Unverified note' or observation.evidence_id in excluded
        findings.append(Finding("unsupported" if unsupported else "possible", f"Public observation: {observation.field}",
            observation.value, "unassessed",
            f"Investigator supplied this observation at {observation.observed_at}; basis: {observation.basis}. "
            + ('Supporting evidence is excluded. ' if observation.evidence_id in excluded else '')
            + 'It is not independently authenticated.',
            [observation.evidence_id] if observation.evidence_id else []))
    for result in case.public_results:
        matched = result.status == 'exact_public_handle'
        findings.append(Finding('possible' if matched else 'unsupported',
            f'Public handle lookup: {result.provider}',
            f'{result.requested_username}: {result.status} at {result.checked_at}.',
            'low' if matched else 'none', result.detail))
    if not case.target_sender:
        findings.append(Finding("unsupported", "Sender analysis unavailable",
            "Select the exact sender label from the export before analyzing message behavior.", "none",
            "No sender was selected. OCR and unattributed plain text are not automatically assigned to the account."))
    else:
        selected = [m for m in case.messages if m.sender == case.target_sender and m.evidence_id not in excluded]
        # Known-time overlaps across exports are counted once. Retain the original records.
        seen = {}
        unique = []
        overlap = 0
        for message in selected:
            key = (message.sender, message.timestamp, message.text)
            if message.timestamp and key in seen and seen[key] != message.evidence_id:
                overlap += 1
                continue
            if message.timestamp:
                seen.setdefault(key, message.evidence_id)
            unique.append(message)
        ids = sorted({m.evidence_id for m in selected})
        n = len(unique)
        findings.append(Finding("verified", "Selected sender sample",
            f"Sender {case.target_sender!r}: {n} text messages; {overlap} same-text, same-time overlaps "
            "excluded from heuristics. Sender-to-account attribution is investigator supplied.", "high",
            "Exact sender-label filtering; counts describe the supplied sample only. "
            "Messages without timestamps cannot be reliably deduplicated across files.", ids))
        if n < 8:
            findings.append(Finding("unsupported", "Insufficient behavioral sample",
                "Fewer than eight attributed text messages; no behavior signal evaluated.", "none",
                "The minimum sample threshold is an engineering safeguard, not a validated statistical cutoff.", ids))
        else:
            counts = Counter(re.sub(r"\s+", " ", m.text.casefold()).strip() for m in unique)
            duplicates = sum(count - 1 for count in counts.values())
            ratio = duplicates / n
            findings.append(Finding("verified", "Text repetition measurement",
                f"{duplicates}/{n} messages repeat an earlier normalized text ({ratio:.1%}); "
                f"largest identical group: {max(counts.values())} messages.", "high",
                "Normalization only folds case and whitespace; punctuation, URLs and wording are preserved.", ids))
            repetition_signal = ratio >= 0.4 and max(counts.values()) >= 3
            if repetition_signal:
                findings.append(Finding("possible", "Repeated text may reflect automation",
                    "The repetition threshold was reached (at least 40% repeats and an identical group of at least three).",
                    "low", "Copy/paste, canned replies, accessibility tools, campaigns or export duplication can also "
                    "produce this pattern. This is not evidence that the account is a bot.", ids))
            timed = [m for m in unique if m.timestamp]
            findings.append(Finding("verified", "Timing coverage",
                f"{len(timed)}/{n} selected messages have usable timezone-aware timestamps.", "high",
                "Missing, malformed and timezone-naive timestamps are omitted, never inferred.", ids))
            timing_signals = 0
            # Separate export files may contain different conversations. Never combine their timing.
            for evidence_id in ids:
                times = sorted(datetime.fromisoformat(m.timestamp).timestamp()
                               for m in timed if m.evidence_id == evidence_id)
                if len(times) < 8:
                    continue
                gaps = [b - a for a, b in zip(times, times[1:])]
                mean = statistics.mean(gaps)
                cv = statistics.pstdev(gaps) / mean if mean > 0 else float("inf")
                findings.append(Finding("verified", "Message interval measurement",
                    f"File {evidence_id}: {len(times)} timed messages; mean gap {mean:.2f}s; "
                    + (f"gap variation CV {cv:.3f}." if mean > 0 else "all timestamps identical."), "high",
                    "Sorted UTC timestamps within one evidence file; population standard deviation / mean gap.", [evidence_id]))
                if all(g > 0 for g in gaps) and 5 <= mean <= 3600 and cv <= 0.1:
                    timing_signals += 1
                    findings.append(Finding("possible", "Regular timing may reflect scheduling",
                        f"File {evidence_id}: at least eight messages, positive gaps, mean 5–3600s, CV ≤ 0.10.",
                        "low", "Scheduled messages, rounding, a short sample or human routines can give regular timing. "
                        "This heuristic has not been calibrated to a bot probability.", [evidence_id]))
                left = peak = 0
                for right, time in enumerate(times):
                    while time - times[left] > 60:
                        left += 1
                    peak = max(peak, right - left + 1)
                if peak >= 10:
                    timing_signals += 1
                    findings.append(Finding("possible", "High message burst rate",
                        f"File {evidence_id}: peak {peak} messages in an inclusive 60-second window (threshold: ten).",
                        "low", "Rapid conversation, pasted fragments, grouped export timestamps or automation can "
                        "produce bursts. Rate alone does not establish automation.", [evidence_id]))
            if not timing_signals and not repetition_signal:
                findings.append(Finding("unsupported", "No configured signal triggered",
                    "The supplied sample did not trigger the configured repetition or timing heuristics.", "none",
                    "Absence of a signal does not establish that the account is human or safe. Coverage may be incomplete.", ids))
    findings.extend([
        Finding("unsupported", "Bot identity is not established", "No bot/human verdict or numerical bot probability is produced.",
                "none", "Heuristics describe patterns in a limited, voluntarily supplied sample."),
        Finding("unsupported", "Account ownership and real-world identity are not established",
                "A matching username does not show that accounts have the same operator or identify an anonymous person.",
                "none", "No identity inference, hidden-contact discovery or leaked-data lookup is performed.")])
    return findings
