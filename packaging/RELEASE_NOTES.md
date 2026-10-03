TRACE now provides downloadable native builds while retaining the Python source workflow.

- Windows x64: per-user setup EXE and portable ZIP with GUI and CLI executables.
- macOS 15+: PKG and app ZIP for Apple Silicon and Intel.
- Kali/Debian amd64: DEB; Linux x64: portable tar.gz.
- Source ZIP, SHA-256 checksums, and native executable validation records.

Every native job must pass automated tests and frozen GUI/CLI smoke checks before these assets are published. GUI checks use synthetic evidence and make no network requests. Interactive installer testing on end-user computers is not performed.

Read [INSTALLERS.md](https://github.com/Jonardi123/TRACE/blob/main/INSTALLERS.md) for installation, architecture selection, and optional local Tesseract OCR. Native builds bundle Python and Tk. Windows/macOS downloads are not publisher-signed or notarized; OS protection checks may block them. Source installation remains available.

Public research remains limited to selected public APIs/indexes; Instagram observations require manual public review. Matching handles do not establish ownership. Behavior signals do not prove that an account is a bot. No private identities, hidden contacts or private messages are retrieved. Cases and case bundles are plaintext and support one writer at a time.
