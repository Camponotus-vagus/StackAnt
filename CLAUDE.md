# CLAUDE.md

Guidance for Claude Code when working in this repo. Keep this file under 200
lines — it is loaded into every session.

## Project

**StackAnt** — PyQt6 GUI that turns a manual-focus-pull video of a specimen
into a focus-stacked composite image. Target users: entomologists doing macro
photography. Cross-platform: Linux (primary dev) + Windows.

Full roadmap is in `docs/PLAN.md`. Do not repeat it here.

## Current state

- v0.1.0 shipped; v0.2.0 in progress on main.
- Two stacking backends: `focus-stack` CLI (existing) and an
  in-process Laplacian-pyramid implementation in
  `stackant/pyramid_stacker.py` with a worker `QThread` and
  guided-filter-smoothed sharpness weights.
- Method radio in StackControls (Pyramid / focus-stack / Auto),
  Compare button, Pyramid-specific Advanced sub-group, compare
  view toggle in the preview panel. See
  `docs/superpowers/specs/2026-04-23-pyramid-stacking-design.md`
  for the full design and
  `docs/superpowers/plans/2026-04-23-pyramid-stacking.md` for the
  task-by-task plan.

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
  preview.py               Stacked-image display + crop
  exporter.py              TIFF + JPEG save
  config.py                Defaults and constants
tests/                     pytest — start with frame_filter
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

## Testing

- `pytest tests/` — unit tests for pure logic (frame filter, decimation, command building)
- Manual smoke test each session: launch app, run the new feature end-to-end
- End-to-end pipeline test video: `/home/francesco/Scaricati/Formiche Uganda/Vid_26-04-22 150856.mp4` (plus other files in that folder)

## Environment notes (this machine)

- Linux Mint, Python 3.12.3, ffmpeg 6.1.1 (apt), git.
- `focus-stack` 1.5 installed at `~/.local/bin/focus-stack` (built from
  PetteriAimonen/focus-stack after `sudo apt install libopencv-dev`).
  The binary lands at `build/focus-stack` — not the repo root — after
  `make`.
- Project-local venv at `.venv/` (gitignored). Activate before running.
- System locale is Italian — subprocess error messages may be localised.
- Dev escape hatch: `STACKANT_ALLOW_MISSING=focus-stack python main.py` lets
  the app launch without focus-stack installed (use during Sessions 2–3
  while focus-stack is not yet built). Do not document this to end users.

## Running

```bash
source .venv/bin/activate
python main.py
```

## Commit style

- One commit per completed session (e.g. `Session 1: app skeleton + dependency checker`)
- Smaller fixup commits within a session are fine
- Never skip hooks; never force-push
- GitHub publishing deferred to Session 8 — do not create a remote without confirmation

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
