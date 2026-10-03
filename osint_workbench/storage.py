import hashlib
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from .core import Case, now


def atomic_write(path: Path, content: str | bytes):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".workbench-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(content.encode("utf-8") if isinstance(content, str) else content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_case(case: Case, directory: Path):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    case.updated_at = now()
    atomic_write(directory / "case.json", json.dumps(case.to_dict(), indent=2, ensure_ascii=False))


def load_case(directory: Path) -> Case:
    path = Path(directory) / "case.json"
    if path.stat().st_size > 100_000_000:
        raise ValueError("Case exceeds the 100 MB loading limit.")
    return Case.from_dict(json.loads(path.read_text(encoding="utf-8")))


def commit_case(case: Case, directory: Path, operation):
    """Keep in-memory state unchanged if validation or an atomic disk save fails."""
    draft = deepcopy(case)
    result = operation(draft)
    save_case(draft, directory)
    case.__dict__.update(draft.__dict__)
    return result


def evidence_bytes(item, directory: Path):
    if Path(item.filename).name != item.filename or item.filename in {'.', '..'}:
        raise ValueError("Invalid stored evidence path.")
    path = Path(directory) / 'evidence' / item.filename
    if path.is_symlink():
        raise ValueError("Symlink evidence is unsupported.")
    raw = read_evidence(path)
    if hashlib.sha256(raw).hexdigest() != item.sha256:
        raise ValueError("Stored evidence has changed; inspect integrity before using it.")
    return raw


def read_evidence(path: Path, limit=20_000_000) -> bytes:
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"Evidence file exceeds {limit // 1_000_000} MB limit.")
    if not raw:
        raise ValueError("Evidence file is empty.")
    return raw


def store_evidence(directory: Path, evidence_id: str, suffix: str, raw: bytes) -> str:
    folder = Path(directory) / "evidence"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    filename = f"{evidence_id}{suffix.lower()}"
    atomic_write(folder / filename, raw)
    return filename


def verify_evidence(case: Case, directory: Path) -> list[tuple[str, str]]:
    results = []
    for item in case.evidence:
        if Path(item.filename).name != item.filename:
            results.append((item.id, "invalid path"))
            continue
        path = Path(directory) / "evidence" / item.filename
        try:
            if path.is_symlink():
                raise ValueError("Symlink evidence is unsupported")
            digest = hashlib.sha256(read_evidence(path)).hexdigest()
            state = "intact" if digest == item.sha256 else "changed"
        except (OSError, ValueError):
            state = "missing or unreadable"
        results.append((item.id, state))
    return results
