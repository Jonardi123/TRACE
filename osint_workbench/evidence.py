from __future__ import annotations

import csv
import hashlib
import io
import json
import warnings
from pathlib import Path

from .core import Case, Evidence, Message, now, public_url, timestamp, uid
from .storage import commit_case, evidence_bytes, read_evidence, store_evidence

MAX_MESSAGES = 10_000
MAX_EVIDENCE = 100
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp'}


def image_metadata(raw):
    from PIL import Image
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 20_000_000:
                raise ValueError('Screenshot exceeds 20 million pixels.')
            return {'width': image.width, 'height': image.height, 'format': image.format,
                    'frames': getattr(image, 'n_frames', 1)}


def parse_messages(raw: bytes, suffix: str) -> tuple[list[dict], list[str]]:
    text = raw.decode("utf-8-sig")
    notices = []
    if suffix == ".json":
        data = json.loads(text)
        # Instagram message_1.json or generic [{sender, text, timestamp}].
        rows = data.get("messages") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("JSON must be a message list or an object containing 'messages'.")
    elif suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or not {"sender", "text"}.issubset(reader.fieldnames):
            raise ValueError("CSV needs sender,text columns; timestamp is optional.")
        rows = list(reader)
    elif suffix == ".txt":
        rows = [{"sender": "", "text": line} for line in text.splitlines() if line.strip()]
        notices.append("Plain text has no sender or timestamp attribution; excluded from sender analysis.")
    else:
        raise ValueError("Message export must be JSON, CSV or UTF-8 TXT.")
    if len(rows) > MAX_MESSAGES:
        raise ValueError("Export exceeds 10,000 rows. Split it into smaller authorized exports.")
    parsed = []
    skipped = invalid_times = unattributed = 0
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Message row {index} must be an object.")
        content = row.get("text", row.get("content", ""))
        if not isinstance(content, str) or not content.strip():
            skipped += 1
            continue
        sender = row.get("sender", row.get("sender_name", ""))
        if not isinstance(sender, str):
            raise ValueError(f"Sender at row {index} must be text.")
        sender = sender.strip()
        if not sender:
            unattributed += 1
        raw_time = row.get("timestamp_ms") if "timestamp_ms" in row else row.get("timestamp")
        time = timestamp(raw_time, milliseconds="timestamp_ms" in row)
        if raw_time not in (None, "") and time is None:
            invalid_times += 1
        parsed.append(dict(sender=sender, text=content, timestamp=time, row=index))
    if skipped:
        notices.append(f"Skipped {skipped} non-text/empty records (attachments and reactions are not analyzed).")
    if invalid_times:
        notices.append(f"Excluded {invalid_times} invalid or timezone-naive timestamps from timing analysis.")
    if unattributed:
        notices.append(f"{unattributed} text records have no sender attribution.")
    if not parsed:
        raise ValueError("No text messages found in this export.")
    return parsed, notices


def screenshot_text(raw: bytes, *, ocr=True) -> tuple[str, float | None, list[str]]:
    from PIL import Image, ImageOps
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP", "TIFF", "BMP"}:
                raise ValueError("Screenshot must be PNG, JPEG, WebP, TIFF or BMP.")
            if image.width * image.height > 20_000_000:
                raise ValueError("Screenshot exceeds 20 million pixels.")
            notices = ["Screenshot authenticity and sender attribution are not established. OCR may misread text."]
            if getattr(image, "n_frames", 1) > 1:
                notices.append("Only the first image frame/page was examined.")
            image.load()
            prepared = ImageOps.exif_transpose(image).convert("RGB")
    if not ocr:
        return "", None, notices + ["OCR disabled; only file metadata and hash recorded."]
    try:
        import pytesseract
        data = pytesseract.image_to_data(prepared, output_type=pytesseract.Output.DICT, timeout=30)
    except (ImportError, RuntimeError, OSError, SystemExit) as exc:
        # Preserve evidence even when the optional system OCR engine is absent.
        return "", None, notices + [f"OCR unavailable ({type(exc).__name__}); install/check Tesseract."]
    lines = {}
    confidences = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = tuple(data[k][i] for k in ("page_num", "block_num", "par_num", "line_num"))
        lines.setdefault(key, []).append(word)
        confidence = float(data["conf"][i])
        if confidence >= 0:
            confidences.append(confidence)
    value = "\n".join(" ".join(words) for words in lines.values())
    mean = round(sum(confidences) / len(confidences), 1) if confidences else None
    if not value:
        notices.append("OCR returned no text. Inspect the screenshot manually.")
    return value, mean, notices


def import_evidence(case: Case, directory: Path, path: Path, *, ocr=True,
                    source_url="", capture_at="", notes="") -> Evidence:
    if len(case.evidence) >= MAX_EVIDENCE:
        raise ValueError("A case supports up to 100 evidence files.")
    source = public_url(source_url) if source_url else ""
    captured = timestamp(capture_at) if capture_at else None
    if capture_at and captured is None:
        raise ValueError("Capture time must be ISO 8601 with a timezone, e.g. 2026-10-03T12:00:00+02:00.")
    suffix = Path(path).suffix.lower()
    if suffix not in IMAGE_SUFFIXES | {'.json', '.csv', '.txt'}:
        raise ValueError('Unsupported evidence extension. Use JSON/CSV/TXT or PNG/JPEG/WebP/TIFF/BMP.')
    raw = read_evidence(path, 5_000_000 if suffix in {".json", ".csv", ".txt"} else 20_000_000)
    digest = hashlib.sha256(raw).hexdigest()
    if any(e.sha256 == digest for e in case.evidence):
        raise ValueError("This exact evidence file is already imported.")
    identifier = uid()
    ocr_text, ocr_confidence = "", None
    rows = []
    if suffix in {".json", ".csv", ".txt"}:
        rows, notices = parse_messages(raw, suffix)
        kind = "messages"
        if len(case.messages) + len(rows) > MAX_MESSAGES:
            raise ValueError("Case exceeds 10,000 text messages.")
    else:
        ocr_text, ocr_confidence, notices = screenshot_text(raw, ocr=ocr)
        kind = "screenshot"
    filename = store_evidence(directory, identifier, suffix, raw)
    item = Evidence(identifier, kind, filename, digest, now(), captured, source, notes,
                    ocr_text, ocr_confidence, notices)
    item.original_filename = Path(path).name
    if kind == 'screenshot':
        item.image_info = image_metadata(raw)
        item.ocr_at = now() if ocr else None
    def add(draft):
        draft.evidence.append(item)
        draft.messages.extend(Message(evidence_id=identifier, **row) for row in rows)
        draft.audit_log.append({'at': now(), 'action': 'evidence_imported', 'evidence_id': identifier,
                                'sha256': digest, 'records': len(rows)})
    try:
        commit_case(case, directory, add)
    except Exception:
        (Path(directory) / 'evidence' / filename).unlink(missing_ok=True)
        raise
    return item


def update_evidence(case, directory, identifier, *, notes, source_url='', capture_at='', excluded=None):
    source_url = public_url(source_url) if source_url else ''
    captured = timestamp(capture_at) if capture_at else None
    if capture_at and captured is None:
        raise ValueError('Capture time requires an ISO 8601 timezone.')
    if excluded is not None and type(excluded) is not bool:
        raise ValueError('Excluded must be a boolean.')
    def edit(draft):
        item = next((e for e in draft.evidence if e.id == identifier), None)
        if item is None:
            raise ValueError('Unknown evidence ID.')
        item.notes, item.source_url, item.capture_at = notes, source_url, captured
        if excluded is not None:
            item.excluded = excluded
        draft.audit_log.append({'at': now(), 'action': 'evidence_annotation_updated',
                                'evidence_id': identifier, 'excluded': item.excluded})
        return item
    return commit_case(case, directory, edit)


def rerun_ocr(case, directory, identifier):
    item = next((e for e in case.evidence if e.id == identifier), None)
    if item is None or item.kind != 'screenshot':
        raise ValueError('Select a screenshot to rerun OCR.')
    raw = evidence_bytes(item, directory)
    text, confidence, notices = screenshot_text(raw)
    def edit(draft):
        target = next(e for e in draft.evidence if e.id == identifier)
        # Keep an existing transcription if the engine fails on a later attempt.
        succeeded = not any('OCR unavailable' in warning for warning in notices)
        if succeeded:
            target.ocr_text, target.ocr_confidence = text, confidence
            target.ocr_at = now()
            target.warnings = notices
        else:
            target.warnings = list(dict.fromkeys(target.warnings + notices))
        target.image_info = image_metadata(raw)
        draft.audit_log.append({'at': now(), 'action': 'ocr_rerun', 'evidence_id': identifier,
                                'status': 'completed' if succeeded else 'unavailable'})
        return target
    return commit_case(case, directory, edit)
