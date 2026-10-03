"""Concise CI progress and parameter IDs, without megabyte-sized byte literals."""
import hashlib
import os


def pytest_make_parametrize_id(config, val, argname):
    if isinstance(val, bytes):
        return f'{argname}-{len(val)}bytes-{hashlib.sha256(val).hexdigest()[:8]}'
    return None


def pytest_runtest_logstart(nodeid, location):
    if os.environ.get('TRACE_TEST_PROGRESS') == '1':
        print(f'\nTRACE test: {nodeid[:200]}', flush=True)
