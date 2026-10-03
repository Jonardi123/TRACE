"""Bound the complete test process, including interpreter and Tk shutdown."""
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    label = sys.argv[1]
    if not label.replace('-', '').isalnum():
        raise SystemExit('Invalid platform label')
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, '-u', '-m', 'pytest', '-q', '--timeout=60',
               '--timeout-method=thread', f'--junitxml=tests-{label}.junit.xml']
    try:
        result = subprocess.run(command, cwd=root, timeout=150)
        raise SystemExit(result.returncode)
    except subprocess.TimeoutExpired:
        print('Test process exceeded 150 seconds, including interpreter shutdown.', flush=True)
        raise SystemExit(1)
