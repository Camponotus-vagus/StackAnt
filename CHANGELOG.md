# Changelog

All notable changes to this project will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

### [1.1] — planned

- **Batch processing:** queue multiple videos, dial in settings once,
  run the whole extract → score → filter → stack → export pipeline on
  each in sequence with per-video + overall progress.
- Optional input downscaling to make GPU stacking viable on
  memory-constrained integrated GPUs.
- Bundled distribution (PyInstaller or similar) so end users don't
  need a Python toolchain.
- Windows end-to-end validation.
