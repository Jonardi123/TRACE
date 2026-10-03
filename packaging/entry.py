"""Frozen GUI/CLI entry point with an offline synthetic GUI smoke check."""
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile

from osint_workbench.__main__ import main, demo


def gui_smoke(output):
    from osint_workbench.gui import TraceApp
    from osint_workbench.storage import load_case
    app = None
    try:
        with tempfile.TemporaryDirectory(prefix='trace-smoke-') as temporary:
            directory = Path(temporary) / 'synthetic-case'
            demo(directory)
            app = TraceApp()
            app.case = load_case(directory)
            app.directory = directory
            app.refresh()
            app.update()
            tabs = []
            for tab in app.tabs.tabs():
                app.tabs.select(tab)
                app.update()
                tabs.append(app.tabs.tab(tab, 'text'))
            assert tabs == ['Instagram', 'Evidence', 'Username research', 'Analysis & report']
            app.run_analysis()
            assert 'Regular timing' in app.finding_text.get('1.0', 'end')
            assert (directory / 'report.html').is_file()
            app.close()
            app = None
        output.write_text(json.dumps({'ok': True, 'tabs': tabs, 'synthetic': True,
                                      'network_requests': 0}, indent=2), encoding='utf-8')
        return 0
    except Exception as exc:
        output.write_text(json.dumps({'ok': False, 'error': str(exc)}), encoding='utf-8')
        return 1
    finally:
        if app is not None:
            app.close()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        raise SystemExit(gui_smoke(Path(sys.argv[2]).resolve()))
    main()
