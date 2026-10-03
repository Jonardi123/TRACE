"""Preserve existing POSIX cooldowns; use a user-writable Windows state folder."""
import os
from pathlib import Path
import sys


def rate_state_directory():
    override = os.environ.get('XDG_STATE_HOME')
    if override:
        base = Path(override)
    elif sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    else:
        base = Path.home() / '.local/state'
    return base / 'osint-workbench'
