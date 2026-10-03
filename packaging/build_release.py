"""Native build, executable smoke checks, and installer/archive assembly."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def zip_tree(folder, output):
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(folder.parent))


def linux_package(folder, release):
    with tarfile.open(release / f'TRACE-{VERSION}-linux-x64.tar.gz', 'w:gz') as archive:
        archive.add(folder, arcname='TRACE')
    with tempfile.TemporaryDirectory(prefix='trace-deb-') as temporary:
        package = Path(temporary)
        shutil.copytree(folder, package / 'opt/trace')
        binary = package / 'usr/bin'
        binary.mkdir(parents=True)
        for name, target in [('trace-osint', 'TRACE'), ('trace-cli', 'trace-cli')]:
            launcher = binary / name
            launcher.write_text(f'#!/bin/sh\nexec /opt/trace/{target} "$@"\n', encoding='utf-8')
            launcher.chmod(0o755)
        desktop = package / 'usr/share/applications'
        desktop.mkdir(parents=True)
        (desktop / 'trace.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=TRACE\nComment=Local public evidence investigation\n'
            'Exec=/opt/trace/TRACE\nTerminal=false\nCategories=Utility;\n', encoding='utf-8')
        control = package / 'DEBIAN'
        control.mkdir()
        (control / 'control').write_text(
            f'Package: trace-osint\nVersion: {VERSION}\nArchitecture: amd64\nMaintainer: TRACE contributors\n'
            'Section: utils\nPriority: optional\nDepends: libc6 (>= 2.35), libx11-6, libxext6, libxrender1, libfontconfig1, libfreetype6\n'
            'Recommends: tesseract-ocr\nDescription: TRACE local public-evidence investigation desktop\n', encoding='utf-8')
        run('dpkg-deb', '--root-owner-group', '--build', package,
            release / f'TRACE-{VERSION}-linux-amd64.deb')


def windows_package(folder, release):
    zip_tree(folder, release / f'TRACE-{VERSION}-windows-x64-portable.zip')
    compiler = shutil.which('ISCC')
    if not compiler:
        candidate = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Inno Setup 6/ISCC.exe'
        if candidate.is_file():
            compiler = str(candidate)
    if not compiler:
        raise RuntimeError('Install official Inno Setup 6 and put ISCC on PATH.')
    run(compiler, f'/DTraceVersion={VERSION}', f'/DTraceSource={folder}',
        f'/DTraceOutput={release}', ROOT / 'packaging/windows.iss')


def mac_package(app, release, arch):
    # ditto preserves application symlinks, which ordinary ZipFile would flatten.
    run('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app,
        release / f'TRACE-{VERSION}-macos-{arch}.zip')
    with tempfile.TemporaryDirectory(prefix='trace-pkg-') as temporary:
        payload = Path(temporary) / 'payload'
        payload.mkdir()
        shutil.copytree(app, payload / 'TRACE.app', symlinks=True)
        component = Path(temporary) / 'component.plist'
        run('pkgbuild', '--analyze', '--root', payload, component)
        # Disable bundle relocation so an existing app elsewhere is not silently targeted.
        import plistlib
        components = plistlib.loads(component.read_bytes())
        for item in components:
            item['BundleIsRelocatable'] = False
        component.write_bytes(plistlib.dumps(components))
        run('pkgbuild', '--root', payload, '--component-plist', component,
            '--install-location', '/Applications', '--identifier', 'io.github.jonardi123.trace',
            '--version', VERSION, release / f'TRACE-{VERSION}-macos-{arch}.pkg')


def main():
    machine = platform.machine().lower()
    arch = 'arm64' if machine in {'arm64', 'aarch64'} else 'x64'
    if sys.platform not in {'win32', 'darwin', 'linux'}:
        raise RuntimeError('Build on Windows, macOS, or Linux.')
    if sys.platform != 'darwin' and arch != 'x64':
        raise RuntimeError('This release configures x64 Linux/Windows and arm64/x64 macOS only.')
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', ROOT / 'packaging/TRACE.spec', cwd=ROOT)
    folder = ROOT / 'dist/TRACE'
    if sys.platform == 'darwin':
        app = ROOT / 'dist/TRACE.app'
        gui = app / 'Contents/MacOS/TRACE'
        cli = app / 'Contents/MacOS/trace-cli'
        docs = app / 'Contents/Resources'
    else:
        app = None
        suffix = '.exe' if sys.platform == 'win32' else ''
        gui, cli = folder / f'TRACE{suffix}', folder / f'trace-cli{suffix}'
        docs = folder
    for name in ('LICENSE', 'INSTALLERS.md'):
        shutil.copyfile(ROOT / name, docs / name)
    evidence = release / f'build-validation-{sys.platform}-{arch}.json'
    with tempfile.TemporaryDirectory(prefix='trace-executable-') as temporary:
        temp = Path(temporary)
        smoke = temp / 'gui.json'
        run(gui, '--self-test', smoke, timeout=90)
        outcome = json.loads(smoke.read_text(encoding='utf-8'))
        if outcome.get('ok') is not True:
            raise RuntimeError(f'Frozen GUI smoke failed: {outcome}')
        doctor = run(cli, 'doctor', capture_output=True, text=True, timeout=30)
        if 'missing' in doctor.stdout.split('Tesseract:')[0]:
            raise RuntimeError('Frozen application is missing Python dependencies.')
        run(cli, 'demo', temp / 'case', capture_output=True, timeout=30)
        report = temp / 'report.html'
        run(cli, 'report', temp / 'case', report, capture_output=True, timeout=30)
        assert 'TRACE / LOCAL EVIDENCE' in report.read_text(encoding='utf-8')
        run(cli, 'bundle', temp / 'case', temp / 'case.zip', capture_output=True, timeout=30)
        with zipfile.ZipFile(temp / 'case.zip') as bundle:
            assert bundle.testzip() is None
        evidence.write_text(json.dumps({'version': VERSION, 'platform': sys.platform,
            'architecture': arch, 'gui': outcome, 'cli_doctor': doctor.stdout,
            'cli_demo_report_bundle': 'passed', 'installer_interactive_test': 'not performed',
            'signed_or_notarized': False}, indent=2), encoding='utf-8')
    if sys.platform == 'win32':
        windows_package(folder, release)
    elif sys.platform == 'darwin':
        mac_package(app, release, arch)
    else:
        linux_package(folder, release)
    assets = sorted(path for path in release.iterdir() if path.is_file() and path.name != 'SHA256SUMS.txt')
    (release / f'SHA256SUMS-{sys.platform}-{arch}.txt').write_text(''.join(
        f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n' for path in assets), encoding='utf-8')
    print(f'Native build, GUI/CLI smoke checks, and packaging completed for {sys.platform}/{arch}.')


if __name__ == '__main__':
    main()
