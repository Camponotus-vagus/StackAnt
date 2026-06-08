# CLAUDE.md

Guidance for Claude Code when working in this repo. Keep this file under 200
lines — it is loaded into every session.

## Project

**StackAnt** — PyQt6 GUI that turns a manual-focus-pull video of a specimen
into a focus-stacked composite image. Target users: entomologists doing macro
photography. Cross-platform: Linux (primary dev) + Windows.

Full roadmap is in `docs/PLAN.md`. Do not repeat it here.

## Current state

- v0.3.0 is the current release — it bundles the v0.2 Laplacian-pyramid
  backend and v0.3 batch processing on top of the v0.1.0 baseline.
- Two stacking backends: `focus-stack` CLI and an in-process
  Laplacian-pyramid stacker (`stackant/pyramid_stacker.py`, worker
  `QThread`, guided-filter-smoothed weights). Method radio in
  StackControls (Pyramid / focus-stack / Auto), Compare button,
  compare view toggle in the preview panel.
- Batch (v0.3): `File ▸ Batch…` scans a folder, queues every video, and
  runs extract → score → auto-filter → stack → export on each in sequence
  (`stackant/batch_controller.py` + `widgets/batch_dialog.py`); output
  alongside each source video, skip-existing, per-video failure isolation.
- Design specs + task plans live in `docs/superpowers/` — Claude-Code-local
  scratch, gitignored (not present in fresh clones).

## Layout

```
main.py                    Entry point (thin — calls stackant.app.main)
stackant/
  app.py                   QApplication bootstrap
  mainwindow.py            QMainWindow + panel layout + signal wiring
  dependency_checker.py    shutil.which() for ffmpeg + focus-stack
  frame_extractor.py       ffmpeg QProcess wrapper
  frame_filter.py          Laplacian variance blur detection + decimation
  stacker.py               focus-stack QProcess wrapper
  pyramid_stacker.py       in-process Laplacian-pyramid stacker (QThread)
  stacking.py              choose_method() heuristic for Auto mode
  batch.py                 batch pure helpers + BatchSettings/BatchItem
  batch_controller.py      sequential batch state machine (QObject)
  folder_loader.py         list_images() for image-folder input
  settings.py              QSettings load/save wrappers
  tempfiles.py             temp-dir tracking + cleanup
  preview.py               Stacked-image display + crop
  thumbnails.py            Pillow-based filmstrip thumbnail rendering
  exporter.py              TIFF + JPEG save
  config.py                Defaults and constants
  widgets/                 controls + stack/filter/export controls,
                           filmstrip, log_panel, preview_panel, batch_dialog
tests/                     pytest (headless Qt — files set QT_QPA_PLATFORM=offscreen)
docs/PLAN.md               Roadmap (don't inline into CLAUDE.md)
```

## Conventions

**UI vs logic separation.** `mainwindow.py` handles layout and signal wiring
only. All algorithms (Laplacian scoring, decimation math, ffmpeg/focus-stack
command building, export) live in their own modules and are testable without Qt.

**Subprocesses.** Always use `QProcess` for `ffmpeg` and `focus-stack`.
Never `subprocess.run()` — it blocks the Qt event loop. Stream stdout/stderr
to a log panel. Provide a cancel button that calls `kill()`.

**Dependency checks.** Run `dependency_checker.check()` at startup before any
workflow operation. Missing tool → non-dismissable dialog with OS-specific
install hints, then `sys.exit(1)`.

**Temp files.** Use `tempfile.mkdtemp(prefix="stackant_")`. Register cleanup
via `atexit` and also on window close. Never write into the input folder.

**Frame format.** Extract to TIFF (lossless) to avoid double-lossy through
JPEG compression of video frames.

**Errors at boundaries only.** Trust internal calls. Validate ffmpeg/focus-stack
exit codes, file reads, user-provided paths. Show errors in the status bar,
not via popup dialogs (popups only for blocking conditions like missing deps).

**Comments.** Default to none. Well-named identifiers do the work. Only
comment non-obvious *why* (a workaround, a tuned constant, a subtle
invariant). Never narrate *what* the code does.

## Gotchas

- **macOS + focus-stack OpenCL.** focus-stack's GPU wavelet kernel crashes on
  macOS' deprecated OpenCL (`can't create cl_mem handle …`). The app auto-retries
  once on CPU with `--no-opencl`, and `config.FOCUS_STACK_NO_OPENCL_DEFAULT` is
  True on Darwin so fresh macOS installs default to CPU. OpenCL-failure detection
  scans the full captured log (the signature can scroll past the tail).

## Testing

- `pytest tests/` — unit tests for pure logic (frame filter, decimation, command building)
- Manual smoke test each session: launch app, run the new feature end-to-end
- End-to-end pipeline test video: `/home/francesco/Scaricati/Formiche Uganda/Vid_26-04-22 150856.mp4` (plus other files in that folder)

## Environment notes

Shared: project-local venv at `.venv/` (gitignored — activate before running);
Italian system locale (subprocess errors may be localised); dev escape hatch
`STACKANT_ALLOW_MISSING=focus-stack python main.py` launches without focus-stack
(do not document to end users).

**Linux (primary dev):** Linux Mint, Python 3.12.3, ffmpeg 6.1.1 (apt).
`focus-stack` 1.5 built from PetteriAimonen/focus-stack after
`sudo apt install libopencv-dev` (binary lands at `build/focus-stack` after `make`),
copied to `~/.local/bin/focus-stack`.

**macOS:** ffmpeg 8.1.1, `focus-stack` 1.5 at `~/.local/bin/focus-stack`. OpenCL is
deprecated here (see Gotchas — CPU `--no-opencl` default). The Linux test-video path
in Testing (above) does not exist on macOS, so video-dependent smoke tests skip.

## Running

```bash
source .venv/bin/activate
python main.py
```

## Commit style

- One commit per completed session (e.g. `Session 1: app skeleton + dependency checker`)
- Smaller fixup commits within a session are fine
- Never skip hooks; never force-push
- Published on GitHub (`origin/main`); push there directly, never force-push

## Known constraints / decisions

- Bundling (PyInstaller etc.) is out of scope for v1.0 — user installs ffmpeg
  and focus-stack themselves. The dep checker's job is to make this obvious.
- QSettings for persistence (no YAML/TOML config files).
- MIT license.

## When unsure

- Re-read `docs/PLAN.md` for the session's acceptance criteria before starting
- Check `TaskList` for session status
- If focus-stack CLI flags change between versions, trust the source repo
  README (PetteriAimonen/focus-stack) over memory
