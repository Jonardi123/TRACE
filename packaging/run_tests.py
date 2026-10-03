"""Bound the complete test process, including interpreter and Tk shutdown."""
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def run_group(selection, output):
    command = [sys.executable, '-u', '-m', 'pytest', '-q', '--timeout=60',
               '--timeout-method=thread', f'--junitxml={output}', *selection]
    process = subprocess.Popen(command, cwd=ROOT)
    try:
        return process.wait(timeout=150)
    except subprocess.TimeoutExpired:
        print('Test process exceeded 150 seconds, including interpreter shutdown.', flush=True)
        if sys.platform == 'win32':
            # Killing only pytest leaves spawned children holding the CI log pipe.
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], check=False, timeout=20)
        else:
            process.kill()
        process.wait(timeout=20)
        return 1


def main(label):
    if not label.replace('-', '').isalnum():
        raise ValueError('Invalid platform label')
    # Fresh interpreter for every GUI check: native Tk interpreter reinitialization
    # is intermittent on Windows. Each process still performs a real GUI test.
    collection = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', 'tests/test_gui.py'],
                                cwd=ROOT, capture_output=True, text=True, check=True, timeout=30)
    nodes = [line for line in collection.stdout.splitlines() if line.startswith('tests/test_gui.py::')]
    if not nodes:
        raise ValueError('No GUI checks collected; refuse to silently skip them.')
    groups = [('core', ['--ignore=tests/test_gui.py'])]
    groups += [(f'gui-{index}', [node]) for index, node in enumerate(nodes)]
    failures = 0
    combined = ET.Element('testsuites', name='TRACE native isolated GUI checks')
    for name, selection in groups:
        output = f'tests-{label}-{name}.junit.xml'
        failures += run_group(selection, output) != 0
        path = ROOT / output
        if path.is_file():
            for suite in ET.parse(path).getroot().findall('testsuite'):
                combined.append(suite)
    ET.ElementTree(combined).write(ROOT / f'tests-{label}.junit.xml', encoding='utf-8', xml_declaration=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
