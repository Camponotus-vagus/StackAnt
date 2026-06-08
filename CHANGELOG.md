# Changelog

All notable changes to this project will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-06-08

### Added

- **Batch processing** (`File ▸ Batch…`): scan a folder, queue every video, and run
  extract → score → auto-filter → stack → export on each in sequence. Settings are
  taken once from the main panel; outputs are written next to each source video as
  `<name>_stacked.tif` / `.jpg`; existing outputs are skipped so an interrupted run
  is resumable; a failed video is logged and the queue continues. Per-video + overall
  progress, with a final done/failed/skipped summary.

### Changed

- The Filter "cap kept frames" control and all Export settings (formats, quality,
  folder) are now editable before a video is loaded or stacked — only the
  *actions* (Auto-threshold, Export) stay gated. This makes batch settings reachable
  up front and lets single-mode users pre-stage their export.

## [0.2.0] — 2026-04-23

### Added

- **Laplacian-pyramid stacking method** alongside `focus-stack`,
  using guided-filter-smoothed sharpness weight maps per pyramid
  level. Same algorithm family as Helicon Focus Method C and Zerene
  PMax. Produces cleaner edges than `focus-stack`'s wavelet path on
  hard contrast boundaries (legs, antennae against bright
  backgrounds). Pure Python/NumPy/OpenCV, CPU-only.
- **Method radio** (Pyramid / focus-stack / Auto) with Pyramid as
  the default. Auto picks by stack size and resolution (≤50 frames
  and longest edge ≤2048 → Pyramid, else focus-stack).
- **Compare methods** button that runs both stackers on the current
  frames and shows both outputs in the preview with a view toggle.
- **Advanced panel** reorganised into method-specific sub-groups;
  three new Pyramid tunables (depth, guided-filter radius, drop
  misaligned frames).
- Log panel prefixes lines with `[pyramid]` / `[focus-stack]`
  during Compare runs.
- Settings persist method + pyramid params across launches.

### Changed

- Dependency: `opencv-python-headless` →
  `opencv-contrib-python-headless` (needed for
  `cv2.ximgproc.guidedFilter`).

### Fixed

- Stopped sending the unsupported `--sharp-strength` flag to
  `focus-stack` (it printed `Warning: unknown options: --sharp-strength=1`
  and did nothing); the inert "Sharpen strength" control is hidden. The
  value is still persisted in case a future `focus-stack` build adds the
  option.
- The Cancel button and window-close now also stop an in-progress
  **Pyramid** run (the default backend), not just `focus-stack` —
  `cancel_requested` and `closeEvent` were only wired to the
  focus-stack stacker.
- macOS: `focus-stack` runs no longer dead-end on the GPU OpenCL
  wavelet kernel (`can't create cl_mem handle for passed UMat
  buffer`). On an OpenCL failure the run now auto-retries once on the
  CPU with `--no-opencl`, and `Disable OpenCL` defaults on for fresh
  macOS installs. OpenCL-error detection scans the full captured log,
  not just the last 800 bytes, so it survives `focus-stack`'s repeated
  progress lines.
- macOS: the log panel uses the system fixed-width font, silencing the
  `qt.qpa.fonts: missing font family "Monospace"` warning.
- Tests: QSettings is isolated to a throwaway INI during the suite, so
  running `pytest` no longer reads or overwrites the user's real
  preferences (export folder, method, OpenCL toggle, …).

## [0.1.0] — 2026-04-23

First functional release.

### Added

- Dependency checker for `ffmpeg` and `focus-stack`; non-dismissable dialog
  with OS-specific install hints when either is missing.
- Video input (MP4/MOV/AVI/MKV) with non-blocking `QProcess`-based frame
  extraction to TIFF, with a decimation spinbox and a cancel button.
- Image-folder input as an alternative to video extraction.
- Laplacian-variance blur scoring with an auto-threshold (mean − 1σ),
  live threshold slider, optional even-spaced decimation cap (targeting
  ~75 frames by default), and double-click / Space per-frame manual
  override.
- Filmstrip view that paints rejected frames with a red tint.
- `focus-stack` integration with default parameters (consistency 2,
  denoise on, sharp strength 1) and an Advanced panel (halo radius,
  free-text extra CLI).
- Preview panel with scaled stacked result (≤ 800 px), click-drag crop
  rectangle that populates a 1:1 detail view, and toggle between the
  stacked result and a selected input frame. Re-stack button re-runs
  `focus-stack` with the current parameters without re-extracting.
- Export to TIFF (byte-for-byte copy) and/or JPEG (quality 60–100 slider,
  subsampling disabled), with auto-name derived from the input stem,
  folder picker, and overwrite confirmation. Successful export reveals
  the output folder in the system file manager.
- Collapsible log panel with Copy / Clear buttons capturing all
  subprocess output.
- QSettings-backed persistence of window geometry, export defaults, and
  focus-stack advanced parameters.
- Keyboard shortcuts: Ctrl+O (open video), Ctrl+Shift+O (open folder),
  Ctrl+E (export), Space (toggle current frame), Ctrl+Q (quit).
- "Disable OpenCL (GPU)" toggle in the stacker's Advanced panel, for
  systems where the OpenCL acceleration path crashes inside
  `focus-stack`. A stack failure containing an OpenCL error also
  surfaces a hint in the status bar.

### Known limitations

- No bundled `ffmpeg` or `focus-stack` binaries — users must install
  both separately.
- Windows testing is unverified on the v0.1.0 dev machine (Linux Mint);
  the code is written to be portable but bug reports welcome.
- Single-file processing only — batch mode is planned for v1.1.
- On very weak integrated GPUs (e.g. Intel Apollo Lake HD 500),
  `focus-stack`'s OpenCL kernels exhaust shared local memory and crash;
  the "Disable OpenCL (GPU)" toggle in Advanced is the workaround.

## Roadmap

### [0.4] — planned

- Optional input downscaling to make GPU stacking viable on
  memory-constrained integrated GPUs.
- Reproducibility manifest on export (JSON sidecar listing kept frame
  paths, Laplacian scores, subprocess commands, tool versions).
- Windows end-to-end validation.

### [0.5] — planned

- Bundled distribution (PyInstaller or similar) so end users don't
  need a Python toolchain.

### [1.0] — stable

- Declared once the milestones above are shipped and verified on
  Linux and Windows without caveats.
