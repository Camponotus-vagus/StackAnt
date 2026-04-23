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
├── main.py                  # Entry point
├── requirements.txt
├── README.md
├── LICENSE
├── assets/
│   └── icon.png
├── stackant/
│   ├── __init__.py
│   ├── app.py               # QApplication setup
│   ├── mainwindow.py        # Main window and layout
│   ├── dependency_checker.py
│   ├── frame_extractor.py   # ffmpeg wrapper
│   ├── frame_filter.py      # Laplacian blur detection + decimation
│   ├── stacker.py           # focus-stack wrapper
│   ├── preview.py           # Thumbnail and crop preview logic
│   ├── exporter.py          # TIFF + JPEG export
│   └── config.py            # Default parameters and constants
└── tests/
    └── test_frame_filter.py
```

## Sessions

### Session 1 — Project Skeleton + Dependency Checker
Working window that launches, checks for ffmpeg and focus-stack, blocks gracefully if missing.

### Session 2 — Video/Image Input + Frame Extraction
Load a video or image folder; extract frames to a temp directory via ffmpeg QProcess.

### Session 3 — Frame Filter (Auto Stability Detection)
Laplacian variance blur detection; auto-threshold mean+1σ; decimation to target 50–100 frames; manual toggle.

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
| Bundling            | Not in v1.0     | Added in v1.1 after core is stable                          |

## Default Parameters (config.py)

```python
FFMPEG_DEFAULT_FORMAT = "tiff"
FRAME_TARGET_COUNT = 75          # Target frames after decimation
LAPLACIAN_THRESHOLD_AUTO = True  # Compute from mean + 1 std dev
FOCUS_STACK_CONSISTENCY = 2
FOCUS_STACK_DENOISE = True
FOCUS_STACK_SHARP_STRENGTH = 1
JPEG_DEFAULT_QUALITY = 95
PREVIEW_MAX_PX = 800
```

## Out of Scope (v1.0)

- Bundled ffmpeg / focus-stack binaries
- Batch processing of multiple videos
- RAW image support
- 3D / anaglyph output
- Cloud sync or remote processing

## Rules for Development

- Dependency checker runs before any workflow — never assume tools are present
- All subprocess calls use QProcess, never blocking subprocess.run()
- Business logic lives in modules separate from UI code
- Each session ends with a working, runnable app
- Test each session with a short MP4 before declaring complete
