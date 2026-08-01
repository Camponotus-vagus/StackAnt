# StackAnt — Build Plan

> Focus stacking GUI for macro entomology photography
> Stack: Python + PyQt6 | Dependencies: ffmpeg, focus-stack (user-installed) | Target: Linux + Windows

## Project Overview

StackAnt is a cross-platform GUI application that takes a video (or folder of
images) of an ant specimen photographed with a manual focus pull, extracts
and filters frames, runs focus stacking, and exports a publication-ready
composite image.

## Repository Structure

```
stackant/
├── main.py                  # Entry point (thin)
├── requirements.txt
├── requirements-dev.txt
├── ruff.toml                # Lint config (rule set frozen by the ruff pin)
├── README.md
├── CHANGELOG.md
├── CITATION.cff             # Citable metadata + ORCID + Zenodo DOI
├── .zenodo.json             # Metadata carried on every Zenodo release
├── LICENSE
├── .github/
│   └── workflows/ci.yml     # Lint (ruff) + pytest on Python 3.10 and 3.12
├── docs/
│   └── PLAN.md
├── assets/
│   ├── icon.svg             # Vector source
│   ├── icon.png
│   ├── screenshot.png
│   ├── demo.gif
│   └── social-preview.png
├── stackant/
│   ├── __init__.py
│   ├── app.py               # QApplication setup
│   ├── mainwindow.py        # Main window, layout, signal wiring
│   ├── dependency_checker.py
│   ├── frame_extractor.py   # ffmpeg wrapper
│   ├── frame_filter.py      # Laplacian blur detection + decimation
│   ├── stacker.py           # focus-stack wrapper
│   ├── pyramid_stacker.py   # in-process Laplacian-pyramid stacker
│   ├── stacking.py          # Auto-method heuristic
│   ├── batch.py             # batch pure helpers + value types
│   ├── batch_controller.py  # sequential batch state machine
│   ├── folder_loader.py     # image-folder input
│   ├── settings.py          # QSettings load/save
│   ├── tempfiles.py         # temp-dir tracking + cleanup
│   ├── preview.py           # Stacked-image display + crop
│   ├── thumbnails.py        # filmstrip thumbnail rendering
│   ├── exporter.py          # TIFF + JPEG export
│   ├── config.py            # Default parameters and constants
│   └── widgets/             # controls, filmstrip, log, preview, batch dialog
└── tests/                   # pytest (headless Qt, offscreen)
```

## Sessions

### Session 1 — Project Skeleton + Dependency Checker
Working window that launches, checks for ffmpeg and focus-stack, blocks gracefully if missing.

### Session 2 — Video/Image Input + Frame Extraction
Load a video or image folder; extract frames to a temp directory via ffmpeg QProcess.

### Session 3 — Frame Filter (Auto Stability Detection)
Laplacian variance blur detection; auto-threshold mean−1σ; decimation to target 50–100 frames; manual toggle.

### Session 4 — Focus Stacking
Run focus-stack via QProcess on selected frames; default and advanced parameters; cancel; log stream.

### Session 5 — Result Preview
Preview stacked.tif (max 800px); click-drag crop region with 1:1 detail view; toggle stacked vs input; re-stack.

### Session 6 — Export
TIFF lossless copy; JPEG with quality slider; auto-name from input; overwrite warning.

### Session 7 — Polish + Cross-Platform Testing
UI polish, shortcuts (Ctrl+O, Ctrl+E, Space), tooltips, error audit, temp cleanup, log panel, QSettings persistence.

### Session 8 — GitHub Release Prep
README with screenshot, pinned requirements, CHANGELOG v0.1.0, tag v0.1.0.

## Key Technical Decisions

| Decision            | Choice          | Rationale                                                   |
|---------------------|-----------------|-------------------------------------------------------------|
| GUI framework       | PyQt6           | Native look, robust file dialogs, QProcess for subprocesses |
| Image processing    | OpenCV + Pillow | OpenCV for Laplacian; Pillow for display and export         |
| Subprocess handling | QProcess        | Non-blocking, integrates with Qt event loop                 |
| Frame format        | TIFF (internal) | Avoid double-lossy from video compression                   |
| Config persistence  | QSettings       | Cross-platform, no extra dependency                         |
| Bundling            | Windows first   | Pulled forward as launch multiplier; pyramid-only + bundled ffmpeg |

## Default Parameters (config.py)

```python
FFMPEG_DEFAULT_FORMAT = "tiff"
FRAME_TARGET_COUNT = 75          # Target frames after decimation
LAPLACIAN_THRESHOLD_AUTO = True  # Compute from mean − 1 std dev
FOCUS_STACK_CONSISTENCY = 2
FOCUS_STACK_DENOISE = True
FOCUS_STACK_SHARP_STRENGTH = 1
FOCUS_STACK_NO_OPENCL_DEFAULT = platform.system() == "Darwin"  # macOS OpenCL is unreliable
JPEG_DEFAULT_QUALITY = 95
PREVIEW_MAX_PX = 800
```

## Out of Scope (v0.1)

- Second stacking algorithm (Laplacian pyramid)  → v0.2
- Batch processing of multiple videos            → v0.3
- Input downscaling for memory-constrained iGPUs → v0.4
- Reproducibility manifest on export             → v0.4
- Bundled ffmpeg / focus-stack binaries          → v0.5
- RAW image support                              → out, no plan
- 3D / anaglyph output                           → out, no plan
- Cloud sync or remote processing                → out, no plan

## Current state

v0.3.1 is the latest release. `main` carries unreleased work on top of it —
performance, accessibility, and CI hardening, no new user-facing features:

- **Performance.** `pyramid_stacker.py` streams frames through a generator and
  aligns them with a `ThreadPoolExecutor`, cutting peak frame memory to O(1)
  instead of holding the whole stack. `frame_filter.score_frames()` scores
  frames in parallel the same way — OpenCV's decode and Laplacian release the
  GIL, so scoring scales across cores while keeping input order and live
  progress updates.
- **Accessibility.** Tooltips and `setAccessibleName` on the filter, stack,
  export, log, and preview controls; keyboard focus and V / C shortcuts on the
  preview panel; "Copied!" feedback on the log copy button.
- **CI hardening.** `ruff` is pinned exactly in `requirements-dev.txt` and the
  rule set is declared in `ruff.toml`. Before the pin an unpinned `ruff>=0.6`
  let release 0.16.1 widen ruff's defaults and turn lint red on `main` and on
  an unrelated PR — 41 violations that no commit had introduced.

Next milestone is v0.5 (Windows installer), pulled ahead of v0.4.

## Roadmap

### v0.2 — Laplacian-pyramid stacking ✅ shipped (0.2.0)

Second in-process stacking backend alongside `focus-stack`, using
guided-filter-smoothed sharpness weight maps per pyramid level. Same
algorithm family as Helicon Focus Method C and Zerene PMax. Motivation:
cleaner edges on hard contrast boundaries (legs, antennae against
bright backgrounds) — the main documented weakness of `focus-stack`'s
wavelet approach.

### v0.3 — Batch processing ✅ shipped (0.3.0)

Queue multiple videos, dial in settings once, run extract → score →
filter → stack → export on each in sequence. Per-video auto-threshold
only. Failures don't abort the queue.

### v0.3.1 — Citation & launch groundwork ✅ shipped (0.3.1)

CITATION.cff + ORCID, Zenodo DOI (concept 10.5281/zenodo.20597239) + badge,
`.zenodo.json`, social-preview card, README demo GIF + Examples gallery,
redesigned ant icon. Public launch in progress; phased playbook and the post
drafts live in the gitignored `promo/` (`README-promo.md`).

### Unreleased — performance, accessibility, CI hardening

On `main`, not yet tagged. See **Current state** above for what landed.

### v0.4 — Polish

- Optional "Downscale inputs to N px" in the stack Advanced panel so
  `focus-stack`'s OpenCL kernels fit on weak integrated GPUs.
- Reproducibility manifest on export (JSON sidecar listing kept frame
  paths, Laplacian scores, subprocess commands, tool versions).
- Windows end-to-end validation.

### v0.5 — Bundled distribution (pulled forward — next, ahead of v0.4)

A Windows installer, pulled ahead as the launch conversion multiplier:
PyInstaller, pyramid-only (no `focus-stack` binary to redistribute), bundled
ffmpeg, unsigned MVP first. macOS (notarized) and Linux follow.

### v1.0 — Stable

Declared once the above are all shipped and verified on Linux and
Windows without caveats.

## Rules for Development

- Dependency checker runs before any workflow — never assume tools are present
- All subprocess calls use QProcess, never blocking subprocess.run()
- Business logic lives in modules separate from UI code
- Each session ends with a working, runnable app
- Test each session with a short MP4 before declaring complete
- CI must be green before merge: `ruff check stackant/ tests/` and `pytest -q`
  on Python 3.10 and 3.12. Keep the ruff pin exact — bumping it is a deliberate
  commit that also carries the fixes for whatever new rules the release adds.
