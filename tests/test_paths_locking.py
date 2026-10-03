import multiprocessing
from pathlib import Path

import pytest
from filelock import FileLock, Timeout

from osint_workbench.paths import rate_state_directory


@pytest.mark.parametrize('platform', ['linux', 'darwin', 'win32'])
def test_explicit_state_override_preserved(monkeypatch, tmp_path, platform):
    monkeypatch.setattr('osint_workbench.paths.sys.platform', platform)
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    assert rate_state_directory() == tmp_path / 'osint-workbench'


def test_windows_state_is_user_writable_location(monkeypatch, tmp_path):
    monkeypatch.setattr('osint_workbench.paths.sys.platform', 'win32')
    monkeypatch.delenv('XDG_STATE_HOME', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    assert rate_state_directory() == tmp_path / 'osint-workbench'


@pytest.mark.parametrize('platform', ['linux', 'darwin'])
def test_existing_posix_rate_location_preserved(monkeypatch, tmp_path, platform):
    monkeypatch.setattr('osint_workbench.paths.sys.platform', platform)
    monkeypatch.delenv('XDG_STATE_HOME', raising=False)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    assert rate_state_directory() == tmp_path / '.local/state/osint-workbench'


def attempt_lock(path, queue):
    try:
        with FileLock(path, timeout=0.1, mode=0o600):
            queue.put('acquired')
    except Timeout:
        queue.put('blocked')


def test_rate_lock_excludes_another_process(tmp_path):
    # Spawn, rather than fork, exercises the same protocol used on Windows/macOS.
    context = multiprocessing.get_context('spawn')
    queue = context.Queue()
    path = str(tmp_path / 'provider.lock')
    with FileLock(path, timeout=1, mode=0o600):
        process = context.Process(target=attempt_lock, args=(path, queue))
        process.start()
        process.join(10)
        assert not process.is_alive()
        assert process.exitcode == 0
        assert queue.get(timeout=2) == 'blocked'
    with FileLock(path, timeout=1, mode=0o600):
        pass
    queue.close()
