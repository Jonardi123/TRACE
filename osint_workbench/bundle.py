"""Portable local archive; includes authorized originals, never uploads them."""
import json
import os
from pathlib import Path
import tempfile
import zipfile

from .core import now, validate_case
from . import __version__
from .report import build_report
from .storage import evidence_bytes


def export_bundle(case, directory, destination):
    destination = Path(destination)
    if destination.suffix.lower() != '.zip':
        raise ValueError('Case bundle destination must end in .zip.')
    if destination.resolve().is_relative_to((Path(directory) / 'evidence').resolve()):
        raise ValueError('Do not place a bundle in the evidence directory.')
    validate_case(case)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.trace-bundle-', dir=destination.parent)
    os.close(fd)
    manifest = {'application': 'TRACE', 'version': __version__, 'exported_at': now(),
                'case_id': case.id, 'includes': 'Case metadata and all original evidence, including excluded files',
                'files': []}
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for item in case.evidence:
                raw = evidence_bytes(item, directory)  # Fail before packaging inconsistent evidence.
                archive.writestr(f'evidence/{item.filename}', raw)
                manifest['files'].append({'path': f'evidence/{item.filename}', 'sha256': item.sha256,
                                          'excluded': item.excluded, 'evidence_id': item.id})
            archive.writestr('case.json', json.dumps(case.to_dict(), indent=2, ensure_ascii=False))
            archive.writestr('report.html', build_report(case, directory))
            archive.writestr('manifest.json', json.dumps(manifest, indent=2))
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
