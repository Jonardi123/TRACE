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
    process = subprocess.Popen(command, cwd=root)
    try:
        raise SystemExit(process.wait(timeout=150))
    except subprocess.TimeoutExpired:
        print('Test process exceeded 150 seconds, including interpreter shutdown.', flush=True)
        if sys.platform == 'win32':
            # Killing only pytest leaves spawned children holding the CI log pipe.
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], check=False, timeout=20)
        else:
            process.kill()
        process.wait(timeout=20)
        raise SystemExit(1)
