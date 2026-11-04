# Sentinel journal

## 2026-11-04 - Startup temp sweep runs rmtree in the shared system temp dir
**Vulnerability:** `tempfiles.sweep_stale()` globbed `stackant_*` in `tempfile.gettempdir()` and rmtree'd any match older than 24h, using symlink-following `is_dir()`/`stat()` and no ownership check. On a multi-user POSIX host (or when run as root) it could act on entries planted or owned by other users.
**Learning:** Subprocess argv building is already hardened (QProcess arg lists, abspath'd inputs, `./` prefix for dash-leading names); the filesystem cleanup paths are the remaining surface that touches data the app did not create.
**Prevention:** Any automatic deletion outside `_TRACKED` must `lstat()`, require a real directory, and require `st_uid == os.getuid()` on POSIX.
