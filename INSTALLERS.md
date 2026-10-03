# Download and install TRACE

Download only the asset matching your operating system and processor from [GitHub Releases](https://github.com/Jonardi123/TRACE/releases). Python, Tk, and Python libraries are bundled. Tesseract is an optional, separately installed OCR engine; screenshots still import and display without it.

| Platform | Download | Installation |
| --- | --- | --- |
| Windows 10/11, x64 | `TRACE-0.2.3-windows-x64-setup.exe` | Run the per-user installer, then open TRACE from Start. No administrator rights needed. |
| Windows, x64 portable | `TRACE-0.2.3-windows-x64-portable.zip` | Extract the **whole** folder into a writable location and run `TRACE.exe`. Keep `_internal` alongside it. `trace-cli.exe` is the CLI. |
| macOS 15+, Apple Silicon | `TRACE-0.2.3-macos-arm64.pkg` or `.zip` | `.pkg` installs `TRACE.app` in Applications; ZIP is a drag-install alternative. |
| macOS 15+, Intel | `TRACE-0.2.3-macos-x64.pkg` or `.zip` | Select x64 on an Intel Mac; install or extract the app. |
| Kali/Debian Linux, amd64 | `TRACE-0.2.3-linux-amd64.deb` | `sudo apt install ./TRACE-0.2.3-linux-amd64.deb`, then launch TRACE from the menu or `trace-osint`. |
| Linux x64, glibc 2.35+ | `TRACE-0.2.3-linux-x64.tar.gz` | Extract the whole folder, then run `./TRACE/TRACE`. CLI: `./TRACE/trace-cli doctor`. Requires a graphical display and X/font libraries. |
| Any supported Python platform | `TRACE-0.2.3-source.zip` | Extract and follow the source installation guide in README.md. |

The macOS installers/apps and Windows executables are **not Developer ID/Authenticode signed or notarized**. Operating-system trust checks may block them. TRACE does not change protection settings; source installation is available if your system will not accept an unsigned installer. On macOS a standard local/ad-hoc PyInstaller signature, when present, is not an Apple Developer ID signature.

`SHA256SUMS.txt` records release file hashes. On Linux run `sha256sum --check SHA256SUMS.txt` in a folder containing the assets to verify (missing undownloaded files will be reported). On macOS use `shasum -a 256 FILE`; on Windows use `Get-FileHash FILE -Algorithm SHA256`. Hashes detect changed downloads; they are not an independent publisher signature.

## OCR

Linux: `sudo apt install tesseract-ocr`. macOS: install Tesseract using your package manager, for example `brew install tesseract`. Windows: install an appropriate Tesseract build linked from the [Tesseract project documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html), add its folder to your user PATH, and restart TRACE. For a macOS app opened from Finder, `/opt/homebrew/bin` and `/usr/local/bin` are not always in its PATH; launch it from a terminal with your Tesseract PATH or use the CLI. Do not copy an engine binary from another OS. Default OCR language is English.

Use the bundled CLI `doctor` to check modules and the engine path. Its Tesseract line honestly says missing when the engine cannot be found. No data is downloaded or sent during these checks.

## Cases and updates

Save cases outside the application installation folder so an uninstall/update cannot remove them. Back up the full case folder. TRACE does not delete cases on uninstall. Cases/bundles are plaintext; select an appropriately protected location. Windows file permissions follow the user's NTFS permissions, rather than POSIX mode 600/700. Rate-limit state uses `%LOCALAPPDATA%/osint-workbench` on Windows and the existing `~/.local/state/osint-workbench` on POSIX; `$XDG_STATE_HOME` overrides the base.

## Build and verification

Each platform is built on its native GitHub runner. Before packaging, the workflow runs pytest (each GUI check uses its own process to avoid reinitializing Tk) and executes the **frozen application**, opens/selects all four GUI tabs using a synthetic case, analyzes it, and exercises CLI dependency checks, demo creation, HTML reporting and case ZIP export. The `build-validation-*.json` release assets record those smoke results. Tests requiring an absent OCR engine are reported as skipped on runners without Tesseract. Interactive installer clicks, real user desktops, Linux distribution coverage and OS signing are not established by those checks.

The GitHub workflow publishes a tagged release only after **all four native jobs pass**. No release asset is claimed merely because a workflow was configured. Test results are downloadable workflow artifacts. GUI smoke data is synthetic and no network action is performed by the executable checks.

To build locally, install the platform's Tk/system build dependencies and native packaging tools (Inno Setup on Windows, Apple's `pkgbuild`/`ditto` on macOS, `dpkg-deb` on Debian Linux), then:

```bash
python -m venv .venv
# Activate the venv using your platform's normal command.
python -m pip install -r requirements-tested.txt -r requirements-build.txt
python -m pip install --no-deps -e .
python packaging/build_release.py
```

Linux needs a display; for headless builds use `xvfb-run -a python packaging/build_release.py`. Build output stays in ignored `dist/`, `build/`, and `release/` folders. Native executables are [platform-specific](https://pyinstaller.org/en/stable/); GitHub uses [native runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
