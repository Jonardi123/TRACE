import argparse
import json
from pathlib import Path

from .analysis import analyze
from .core import Case, Observation, now, username
from .evidence import import_evidence, rerun_ocr, update_evidence
from .bundle import export_bundle
from .research import PublicResearch, record_research
from .report import export_report
from .storage import load_case, save_case
from .workflow import ACCESS_STATUSES, review_access


def demo(directory: Path):
    """Synthetic data only; no lookup of a real account."""
    if (directory / "case.json").exists():
        raise ValueError("Demo destination already contains a case; choose a new folder.")
    from datetime import datetime, timedelta, timezone
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    case = Case("example_demo_handle", target_sender="Demo sender")
    case.observations.append(Observation("Biography", "SYNTHETIC DEMO — no real account investigated",
                            "https://example.org/demo", now(), basis='Unverified note'))
    records = [{"sender": "Demo sender", "text": "Hello, this is a synthetic repeated message.",
                "timestamp": (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=30 * i)).isoformat()}
               for i in range(12)]
    source = directory / "synthetic-messages.json"
    source.write_text(json.dumps(records, indent=2))
    import_evidence(case, directory, source, notes="Generated synthetic demonstration; no real messages.")
    source.unlink()
    save_case(case, directory)
    export_report(case, directory, directory / "report.html")
    return directory / "report.html"


def main():
    parser = argparse.ArgumentParser(description="TRACE: local public-evidence OSINT investigation")
    sub = parser.add_subparsers(dest="command")
    gui_parser = sub.add_parser("gui", help="Open the graphical interface (default)")
    gui_parser.add_argument('--case', dest='directory', type=Path, help='Open an existing case folder on launch')
    sub.add_parser('doctor', help='Check local dependencies without searching or exposing credentials')
    demo_parser = sub.add_parser("demo", help="Generate a synthetic case and HTML report without networking")
    demo_parser.add_argument("directory", type=Path)
    new_parser = sub.add_parser("new", help="Create a case")
    new_parser.add_argument("username")
    new_parser.add_argument("directory", type=Path)
    import_parser = sub.add_parser("import", help="Import a voluntarily supplied evidence file")
    import_parser.add_argument("directory", type=Path)
    import_parser.add_argument("file", type=Path)
    import_parser.add_argument("--no-ocr", action="store_true")
    import_parser.add_argument("--source-url", default="")
    import_parser.add_argument("--capture-at", default="")
    import_parser.add_argument("--notes", default="")
    analysis_parser = sub.add_parser("analyze", help="Analyze an exact sender label")
    analysis_parser.add_argument("directory", type=Path)
    analysis_parser.add_argument("--sender", default=None)
    report_parser = sub.add_parser("report", help="Export an HTML report")
    report_parser.add_argument("directory", type=Path)
    report_parser.add_argument("output", type=Path)
    report_parser.add_argument("--include-text", action="store_true")
    research_parser = sub.add_parser('research', help='Check exact public GitHub/GitLab handles; no API key required')
    research_parser.add_argument('directory', type=Path)
    research_parser.add_argument('--provider', choices=['GitHub', 'GitLab'], action='append')
    research_parser.add_argument('--state-dir', type=Path, default=None)
    review_parser = sub.add_parser('review', help='Record an investigator-supplied Instagram access review')
    review_parser.add_argument('directory', type=Path)
    review_parser.add_argument('--status', choices=ACCESS_STATUSES, required=True)
    review_parser.add_argument('--checked-at', default='')
    review_parser.add_argument('--notes', default='')
    ocr_parser = sub.add_parser('ocr', help='Rerun local OCR on a stored screenshot')
    ocr_parser.add_argument('directory', type=Path)
    ocr_parser.add_argument('evidence_id')
    evidence_parser = sub.add_parser('evidence', help='Edit annotations or exclude/restore an evidence file')
    evidence_parser.add_argument('directory', type=Path)
    evidence_parser.add_argument('evidence_id')
    evidence_parser.add_argument('--notes', default=None)
    group = evidence_parser.add_mutually_exclusive_group()
    group.add_argument('--exclude', action='store_true')
    group.add_argument('--restore', action='store_true')
    bundle_parser = sub.add_parser('bundle', help='Export a local ZIP containing case metadata and original evidence')
    bundle_parser.add_argument('directory', type=Path)
    bundle_parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        if args.command in (None, "gui"):
            from .gui import launch
            launch(getattr(args, 'directory', None))
        elif args.command == 'doctor':
            import importlib.util
            import shutil
            import sys
            print(f'Python {sys.version.split()[0]}')
            for module in ['tkinter', 'PIL', 'pytesseract', 'requests', 'filelock']:
                print(f'{module}: ' + ('available' if importlib.util.find_spec(module) else 'missing'))
            print('Tesseract: ' + (shutil.which('tesseract') or 'missing (screenshots import without OCR)'))
        elif args.command == "demo":
            print(demo(args.directory).resolve())
        elif args.command == "new":
            if (args.directory / "case.json").exists():
                raise ValueError("Case already exists; choose another directory.")
            save_case(Case(username(args.username)), args.directory)
            print((args.directory / "case.json").resolve())
        elif args.command == "import":
            case = load_case(args.directory)
            item = import_evidence(case, args.directory, args.file, ocr=not args.no_ocr,
                                   source_url=args.source_url, capture_at=args.capture_at, notes=args.notes)
            print(f"Imported {item.id}; " + "; ".join(item.warnings))
        elif args.command == "analyze":
            case = load_case(args.directory)
            if args.sender is not None:
                if args.sender not in {m.sender for m in case.messages if m.sender}:
                    raise ValueError("Sender must exactly match a nonempty sender label from the export.")
                case.target_sender = args.sender
                save_case(case, args.directory)
            print(json.dumps([f.__dict__ for f in analyze(case)], indent=2, ensure_ascii=False))
        elif args.command == "report":
            export_report(load_case(args.directory), args.directory, args.output, include_text=args.include_text)
            print(args.output.resolve())
        elif args.command == 'research':
            case = load_case(args.directory)
            results = PublicResearch(state_dir=args.state_dir).research(case.username, args.provider or ('GitHub', 'GitLab'))
            record_research(case, args.directory, results)
            print(json.dumps([r.__dict__ for r in results], indent=2))
        elif args.command == 'review':
            case = load_case(args.directory)
            review_access(case, args.directory, args.status, args.checked_at, args.notes)
            print(json.dumps(case.instagram_review.__dict__, indent=2))
        elif args.command == 'ocr':
            item = rerun_ocr(load_case(args.directory), args.directory, args.evidence_id)
            print(f'OCR score: {item.ocr_confidence}; ' + '; '.join(item.warnings))
        elif args.command == 'evidence':
            case = load_case(args.directory)
            item = next((e for e in case.evidence if e.id == args.evidence_id), None)
            if item is None:
                raise ValueError('Unknown evidence ID.')
            excluded = True if args.exclude else False if args.restore else None
            update_evidence(case, args.directory, item.id, notes=args.notes if args.notes is not None else item.notes,
                            source_url=item.source_url, capture_at=item.capture_at or '', excluded=excluded)
            print('Evidence annotation updated; original retained.')
        elif args.command == 'bundle':
            export_bundle(load_case(args.directory), args.directory, args.output)
            print(args.output.resolve())
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
