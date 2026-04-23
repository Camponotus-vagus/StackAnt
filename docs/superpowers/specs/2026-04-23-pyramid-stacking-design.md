# StackAnt v0.2 — Laplacian-pyramid stacking

**Status:** approved, ready for implementation plan
**Target release:** v0.2
**Author:** brainstormed 2026-04-23

## Context and motivation

StackAnt v0.1.0 shells out to Petteri Aimonen's `focus-stack` CLI, which
uses complex-wavelet fusion. The approach is fast and solid but has two
documented weaknesses:

- **Halos at hard contrast edges** — most visible on entomology subjects
  where thin dark structures (legs, antennae, setae) cross bright
  backgrounds.
- **Color fringing** near those halos as a side-effect of its colour
  reassignment step.

The commercial tools that dominate the entomology workflow — Helicon
Focus (Method C) and Zerene Stacker (PMax) — use Laplacian-pyramid
fusion with guided-filter-smoothed sharpness weight maps. Same
algorithm family. Different failure mode (occasional contrast
over-boost vs. wavelet halos), and in direct comparisons on macro
specimens the pyramid path usually produces cleaner edges.

v0.2 adds a pure-Python Laplacian-pyramid stacker as a **second
in-process method alongside `focus-stack`**, addressing the halo
weakness specifically for entomology use cases.

## Goals

- Give the user a second, halo-cleaner stacking method without adding
  a C/C++ build step or a GPU requirement.
- Preserve the existing `focus-stack` path unchanged — it is still the
  fastest option and the right default for deep stacks or 4K+ inputs.
- Offer an opt-in **Compare** mode that runs both methods so the user
  can eyeball the quality difference on their own specimens (the honest
  way to choose, per published community guidance).
- Provide an **Auto** method choice for users who don't want to think
  about it — a documented heuristic, not a claim of correctness.

## Non-goals (explicit deferrals)

| Feature | Deferred to |
|---|---|
| Manual retouching brush (Zerene-style paint-from-source) | v0.6+ or never |
| AI/ML stacker (StackMFF, Araujo 2023, diffusion methods) | research-only, no commitment |
| Replacing `focus-stack` | never — it stays as a first-class method |
| Batch mode (running v0.2's pyramid across multiple videos) | v0.3 |
| Reproducibility JSON manifest | v0.4 |
| Windows end-to-end validation specific to pyramid path | v0.4 |
| Side-by-side Compare layout in the preview panel | v0.2 ships toggle; side-by-side reconsidered later |

Subject-type auto-detection (bristly → pyramid, smooth → focus-stack)
is explicitly **not** attempted. No published guidance supports it
and per-image classification is out of scope for a classical stacker.

## Architecture

The pyramid stacker is **additive**. Nothing about the existing
`focus-stack` wrapper changes.

### New files

- **`stackant/pyramid_stacker.py`** — `PyramidStacker(QObject)`,
  shaped identically to `stackant/stacker.py::FocusStacker`: emits
  `progress(int)`, `log(str)`, `finished_ok(str)`, `failed(str)`,
  `cancelled()`. Runs its computation in a worker `QThread` because
  NumPy/OpenCV blocks the Qt event loop.
- **`stackant/stacking.py`** — pure functions:
    - `choose_method(n_frames: int, width: int, height: int) -> str` —
      returns `"pyramid"` or `"focus-stack"`, implementing the Auto
      heuristic (see UX section).
    - Nothing else — the Compare orchestration lives in MainWindow as
      plain signal-slot chaining, not a new class.

### Modified files

- **`stackant/mainwindow.py`**: owns both stackers; dispatches based
  on the method picker; handles Compare as a new `_on_compare_requested`
  signal flow that chains Pyramid first, then `focus-stack`, and
  collects both outputs. Order is fixed: Pyramid is the v0.2 showcase
  method and running it first gives the user something to inspect in
  the preview while `focus-stack` finishes.
- **`stackant/widgets/stack_controls.py`**: adds the three-way method
  radio, the Compare button at full width parity with Stack Frames,
  and restructures the Advanced collapsed area into two sub-group-boxes
  (one for `focus-stack`, one for `Pyramid`) each with its own tunables.
- **`stackant/widgets/preview_panel.py`**: gains a `View: Pyramid ↔
  focus-stack` toggle button above the main preview, visible only when
  two stacked outputs exist (i.e. after a successful Compare). Swaps
  the main preview pixmap and updates the crop-detail pane on flip.
  Existing `Show input frame` toggle is independent and unchanged.
- **`stackant/widgets/log_panel.py`**: `append_tagged(tag: str, text:
  str)` helper prepending `[tag] ` to each line. Used by MainWindow
  during Compare runs; single-method runs remain unprefixed.
- **`stackant/settings.py`**: four new keys (see Settings section),
  same QSettings type-coercion pattern already in place.

### Dependency change

`requirements.txt`: **`opencv-python-headless==4.13.0.92`** →
**`opencv-contrib-python-headless==4.13.0.92`**. The `contrib` wheel
is a strict superset; the only new API we use is
`cv2.ximgproc.guidedFilter`. No other dependency change.

Wheel size impact: `opencv-contrib-python-headless` is ~40 % larger
than `opencv-python-headless`. CI install cache absorbs this; bundled
distribution (v0.5) will weigh the cost then.

## Algorithm

### Pipeline

Given `N` kept frames (already filtered by StackAnt's Laplacian-variance
gate and decimation cap, typically 20–100):

1. **Alignment** (~20 % of runtime).
   - `cv2.findTransformECC` with `MOTION_AFFINE` motion model.
   - Reference frame = the middle frame (index `N // 2`).
   - Neighbour-to-neighbour chaining — frame `i` is aligned to frame
     `i+1` (or `i-1` on the far side of the reference), and
     transformations compose toward the reference.
   - Termination: `TERM_CRITERIA_EPS + COUNT`, `count=100`, `eps=1e-4`.
   - Failure handling: ECC throws `cv2.error` if it fails to converge.
     If the **drop misaligned frames** toggle is on (default), that
     frame is skipped with a `[pyramid] WARN: frame N alignment
     failed, dropped` log line and the stack continues with the rest.
     If all frames fail, the run aborts with a clear status message.

2. **Pyramid construction.**
   - Pyramid depth `L = max(3, floor(log2(min(h, w))) - 3)` by default
     (5–7 levels at 1080p, 6–8 at 6K). User can override.
   - For each aligned frame, build:
     - A Gaussian pyramid `G_0, G_1, …, G_L` (G_0 is the frame).
     - A Laplacian pyramid `L_k = G_k − upsample(G_{k+1})` for
       `k = 0 … L-1`, plus the bottom Gaussian `G_L` as the base.
   - Implemented with `cv2.pyrDown` and `cv2.pyrUp` — the textbook
     Burt-Adelson recipe.

3. **Per-level sharpness map.**
   - Sum-Modified-Laplacian (SML): for each pyramid level's grayscale
     component, compute `|∂²/∂x²| + |∂²/∂y²|` with a 1D Laplacian
     kernel per axis, then sum in a small window (`7×7`).
   - Produces one scalar sharpness score per pixel per level per
     source frame.

4. **Guided-filter smoothing.**
   - `cv2.ximgproc.guidedFilter(guide=source_RGB_level, src=sharpness,
     radius=R, eps=0.01**2)` where `R` is the guided-filter radius
     (default 8, user-tunable).
   - This step is the quality differentiator — it's what stops the
     raw sharpness map from creating speckle/blocking artifacts and
     what edge-preservingly aligns the weight map to the source image.

5. **Fusion.**
   - At each pyramid level, normalise smoothed sharpness maps across
     the `N` frames so they sum to 1 per pixel.
   - Weighted sum of Laplacian coefficients at that level.

6. **Collapse.**
   - Standard pyramid reconstruction: starting from the fused bottom
     Gaussian, repeatedly `pyrUp` and add the fused Laplacian of the
     next level, up to full resolution.

7. **Output.**
   - Write to `{temp_dir}/stacked_pyramid.tif` as 8-bit TIFF via
     OpenCV / Pillow. Matches focus-stack's output bit depth; 16-bit
     TIFF is a future-work item (not in v0.2 scope).

### Tunables exposed in Advanced

| Control | Default | Notes |
|---|---|---|
| Pyramid depth | auto | Override as int; 0 to auto-compute |
| Guided-filter radius | 8 | 4–32 is the sensible range |
| Drop misaligned frames | on | If off, ECC failure aborts the run |

Defaults picked so a first-time user never opens Advanced.

### Progress reporting

The worker emits progress with stage-weighted percentages:

| Stage | Percent range |
|---|---|
| Alignment | 0 – 25 |
| Pyramid build | 25 – 40 |
| Sharpness + guided filter | 40 – 75 |
| Fusion + collapse | 75 – 95 |
| Output write | 95 – 100 |

Stage label appears in the status bar; bar tracks within-stage
progress. Worker also emits `log` messages per stage boundary.

### Cancellation

Worker checks a shared `_cancelled` boolean (guarded by a simple
`threading.Event` for thread safety) between frames and between
stages. `cancel()` sets the event; the worker exits cleanly mid-stage
on the next check, deletes any partial output file, and emits
`cancelled()`. Main thread never blocks on the worker.

### Memory

Peak memory at level 0 is roughly `N × H × W × 3 × 4 bytes ×
2` (Gaussian + Laplacian storage before collapse). For `N=40` at
`1920×1080` → ~2 GB, comfortably fitting on the 8 GB LapBook Air.
We build pyramids eagerly and free per-level storage once it's been
fused and collapsed, so the peak is bounded to level 0 + immediate
next level. Streaming / windowed execution for larger stacks is a
v0.3+ concern.

### Expected runtime

On the LapBook Air (Intel N3350 / HD 500), 40 frames, 1080p, CPU only:

| Stage | Estimated |
|---|---|
| Alignment | ~10 s |
| Pyramid build | ~5 s |
| Sharpness + guided filter | ~25 s |
| Fusion + collapse | ~5 s |
| **Total** | **~45 s** |

Same ballpark as `focus-stack --no-opencl` (~52 s on the same hardware),
with cleaner edges as the tradeoff. On hardware where `focus-stack`
can use its OpenCL path (not HD 500), `focus-stack` is ~3× faster and
the speed gap becomes the reason Auto picks `focus-stack` for bigger
inputs.

## UX

### Stack controls group box

New layout, top to bottom:

1. **Method radio** — three options, one visible at a time:
   `Pyramid` / `focus-stack` / `Auto`. Default `Pyramid`.
2. **Stack Frames** + **Cancel** buttons (existing).
3. **Compare methods** button — full width, same visual weight as
   Stack Frames. Enabled whenever `_ready` (at least one kept frame);
   the method radio is ignored because Compare always runs both
   methods.
4. **Advanced options ▾** toggle (existing, collapsed by default).
5. Inside Advanced, **two sub-group-boxes**:
   - **focus-stack** — all existing controls unchanged
     (consistency, denoise, sharp-strength, halo radius, Disable
     OpenCL, Extra CLI flags).
   - **Pyramid** — pyramid depth (spinbox or "auto"), guided-filter
     radius (spinbox), drop misaligned frames (checkbox).

### Tooltips

Every new control has a tooltip. Key ones:

- **Pyramid radio**: *Laplacian-pyramid fusion with guided-filter
  smoothing. Slower, better edges (cleaner on legs/antennae). Same
  algorithm family as Helicon "Method C" and Zerene "PMax".*
- **focus-stack radio**: *Complex-wavelet fusion via the focus-stack
  CLI. Faster, GPU-accelerated when available. Slightly more
  halo-prone at hard contrast edges.*
- **Auto radio**: *Picks a method based on stack size and resolution:
  Pyramid for ≤50 frames at ≤2K (the common-case quality winner),
  focus-stack otherwise. There is no universal best — for
  quality-critical work, use Compare.*
- **Compare button**: *Runs both stackers on the current frames and
  shows them side-by-side in the preview. Takes roughly twice as long
  as a single stack.*
- **Pyramid depth**: *Number of Laplacian pyramid levels. Higher =
  coarser structure captured, slower. Auto picks based on image size.*
- **Guided-filter radius**: *Smoothing window for the sharpness
  weight map. Higher = smoother transitions, fewer speckle artifacts,
  risk of losing fine detail.*

### Auto heuristic

```python
def choose_method(n_frames: int, width: int, height: int) -> str:
    """Pick a stacking method when the user selects Auto.

    Documented heuristic — no published rule exists. Pyramid wins on
    small-to-medium stacks at ≤2K because the edge-quality gain
    matters and the speed cost is small. focus-stack wins on deeper
    stacks or 4K+ because its GPU path is substantially faster and
    the quality gap narrows on deep stacks.
    """
    n_ok = n_frames <= 50
    res_ok = max(width, height) <= 2048
    return "pyramid" if (n_ok and res_ok) else "focus-stack"
```

Resolution gate is **longest edge ≤ 2048 px** (covers 1080p, 2K DCI,
UHD-2K-variants; rejects 4K UHD and above).

### Preview panel

Additions only — nothing removed:

- Above the main scaled preview, a small button row appears **when
  two stacked outputs exist**. Label: `View: <current>` where
  `<current>` is `Pyramid` or `focus-stack`. Click cycles through
  the two.
- Below the preview (where `Re-stack` already lives): no change.
- Crop-detail pane: updates in-place when the main preview swaps.
- Existing `Show input frame` toggle is independent — works
  regardless of which stacked output is the current view.

### Log panel during Compare

- Compare launches pyramid first, then focus-stack (arbitrary order;
  both will run). Their `log` signals are connected with prefixed
  writers (`append_tagged("pyramid", …)` etc.) for the duration of
  the Compare run.
- Command-ready lines stay as-is (`$ focus-stack …` and `$ python
  pyramid-stacker …` pseudo-command for transparency).
- Single-method runs are unprefixed.

## Settings and persistence

Adds to the `stack/` namespace. All reads use QSettings `type=`
coercion with a default so corrupted values fall back silently.

| Key | Type | Default | Notes |
|---|---|---|---|
| `stack/method` | str | `"pyramid"` | `"pyramid"` / `"focus-stack"` / `"auto"` |
| `stack/pyramid/depth` | int | `-1` | `-1` = auto; >0 overrides |
| `stack/pyramid/guided_radius` | int | `8` | Clamped to [4, 32] on load |
| `stack/pyramid/drop_misaligned` | bool | `True` | |

Existing v0.1.0 focus-stack keys are **not** migrated or renamed.
Users upgrading inherit their tuning intact.

## Error handling

| Condition | Behaviour |
|---|---|
| ECC alignment fails on one frame, `drop_misaligned=True` | Log a warning, drop the frame, continue. |
| ECC alignment fails on one frame, `drop_misaligned=False` | Abort the run; `failed(...)` with the frame index in the message. |
| ECC alignment fails on all frames | Abort; `failed("All N frames failed alignment. Subject may be moving.")` |
| `MemoryError` during pyramid build | Abort; `failed("Out of memory on pyramid build. Try fewer frames or lower the decimation cap.")` |
| Pyramid cancelled by user | `cancelled()` signal; status bar shows "Pyramid stacking cancelled." (consistent with existing cancel UX). |
| Compare: first method fails | Log the failure with `[method]` prefix; proceed to the second method. Final status reflects both outcomes. |
| Compare: first method cancelled | Stop entirely, don't launch the second. The first method's `cancelled` signal is handled as usual; the second method is never started. |
| Compare: both methods fail | `failed(combined_message)` with both failure reasons in the log. |
| `opencv-contrib-python-headless` not installed | Import guard in `pyramid_stacker.py`; MainWindow detects this and disables the Pyramid radio and the Compare button, with a tooltip "install opencv-contrib-python-headless to enable the Pyramid stacker". App keeps working in focus-stack-only mode. |

Existing OpenCL-error hint mechanism on `focus-stack` failures is
unchanged.

## Testing

### Unit tests (no Qt)

**`tests/test_pyramid_stacker.py`**

- Laplacian pyramid build + collapse round-trip on a 256×256 synthetic
  image → should recover to within small numeric ε.
- SML computation on a known constant image (zero everywhere) and a
  known step-edge image (nonzero at the edge only).
- `cv2.ximgproc.guidedFilter` availability check — if unavailable,
  test is skipped with a clear message.
- 2-frame fusion rule: source A is sharp, source B is Gaussian-blurred
  version of A. Assert fused image's SML > B's SML at every pixel
  and ≤ A's SML (blended toward the sharp source).
- Cancellation: run a fusion on a 10-frame synthetic stack in a
  worker thread; cancel after N ms; assert the thread exits cleanly
  within 2 s and emits `cancelled()`.

**`tests/test_stacking_auto.py`**

- Boundary cases for `choose_method`:
  - `(50, 1920, 1080)` → `"pyramid"`
  - `(51, 1920, 1080)` → `"focus-stack"`
  - `(30, 2049, 1080)` → `"focus-stack"` (longest edge > 2048)
  - `(30, 2048, 2048)` → `"pyramid"` (exactly at threshold)
  - `(1, 100, 100)` → `"pyramid"`
  - `(0, 100, 100)` → raises `ValueError("no frames")`

### Headless-smoke tests (extend `tests/test_headless_smoke.py`)

- `TestMethodPicker`: radio initial default is Pyramid; each radio is
  selectable; choice persists across `MainWindow` close/reopen.
- `TestCompareFlow` (marked skip if video absent): load real Uganda
  video, extract at decimation=200 (≤10 frames), filter, click
  Compare, wait for both stackers to finish, assert both output files
  exist and the preview toggle appears.
- `TestPyramidSingleRun` (synthetic 3-frame tiny stack): switch radio
  to Pyramid, run Stack Frames, assert `stacked_pyramid.tif` exists
  and status bar says Stack complete.
- QSettings roundtrip covers `stack/method`,
  `stack/pyramid/guided_radius`, etc.

### Manual verification (required before merge)

- Run the full Uganda-ant pipeline under each method with the same
  frame set; capture before/after crops of a known halo region (one
  of the leg-against-sky zones visible in the existing README
  screenshot); attach both to the PR description.
- Compare mode run on the same clip; verify the preview toggle flips
  between both outputs cleanly and the log panel shows clear
  `[pyramid]` / `[focus-stack]` prefixing.
- Full CI run passes on Python 3.10 and 3.12 with the
  `opencv-contrib-python-headless` swap.

### Not tested automatically (acknowledged)

- Subjective visual quality comparison — deferred to manual
  spot-checks in PR review.
- Performance benchmarks (wall-clock per method per hardware tier) —
  interesting, out of scope for v0.2.

## Open questions

None blocking. Noted for later:

- Whether to add 16-bit TIFF output — useful for scientific use but a
  separate feature; tracked for v0.3 or later.
- Whether `choose_method` should consider per-frame decimation history
  (e.g. heavily decimated stacks may have more motion between frames)
  — no data yet to suggest this is worth it.
- Whether Compare mode should be wired to the `Re-stack with current
  params` button in the preview panel (so the Re-stack button becomes
  context-aware). Deferred; current behaviour (Re-stack uses the
  single current method) is clear and predictable.

## Changelog snippet (to add on release)

```markdown
## [0.2.0] — <date>

### Added

- **Laplacian-pyramid stacking method** alongside `focus-stack`,
  using guided-filter-smoothed sharpness weight maps per pyramid
  level. Same algorithm family as Helicon Focus Method C and Zerene
  PMax. Produces cleaner edges than `focus-stack`'s wavelet path on
  hard contrast boundaries (legs, antennae against bright
  backgrounds).
- **Method radio** (Pyramid / focus-stack / Auto) with Pyramid as
  the default. Auto picks by stack size and resolution.
- **Compare button** that runs both stackers and shows both outputs
  in the preview with a view-toggle.
- **Advanced panel** reorganised into method-specific sub-groups;
  three new pyramid tunables (depth, guided-filter radius, drop
  misaligned frames).
- Log panel prefixes lines with `[pyramid]` / `[focus-stack]` during
  Compare runs.

### Changed

- Dependency: `opencv-python-headless` → `opencv-contrib-python-headless`
  (needed for `cv2.ximgproc.guidedFilter`).
```
