
## 2025-05-15 - [Grayscale Guide for Guided Filter]
**Learning:** Using a 1-channel grayscale guide for `cv2.ximgproc.guidedFilter` is ~2x faster than a 3-channel RGB guide and sufficient for weight map smoothing in Laplacian pyramids.
**Action:** Always prefer grayscale guides for smoothing masks unless color-specific guidance is strictly required.

## 2025-05-15 - [Cumulative Fusion Loop]
**Learning:** Stacking all per-image weight maps into a single array for normalization (`np.stack`) creates a massive memory bottleneck (O(N * H * W)).
**Action:** Use cumulative accumulation (`fused += w * band`, `total_weight += w`) to reduce peak memory by ~50% in image fusion pipelines.

## 2025-05-15 - [Streaming and Parallel Alignment]
**Learning:** Loading all input frames into memory before processing is a significant memory bottleneck for large focus stacks. Using a generator-based stream and parallelizing the alignment step with `ThreadPoolExecutor` allows for O(1) frame memory overhead and faster execution.
**Action:** Stream heavy image data through generators and use parallel executors for independent CPU-bound image processing tasks like alignment.

## 2025-05-15 - [Parallel Frame Scoring]
**Learning:** Sequential frame scoring (`score_frames`) using `cv2.imread` and `cv2.Laplacian` blocks CPU threads and scales poorly (O(N) sequentially). Since these OpenCV operations release the GIL, they are ideal for parallelization via a Python `ThreadPoolExecutor`.
**Action:** Use multi-threaded `ThreadPoolExecutor` to parallelize heavy OpenCV-based image analysis operations such as frame blur scoring, and use `as_completed` combined with pre-allocated result lists to maintain real-time UI progress tracking and exact original 1:1 input ordering.

## 2025-05-15 - [Fast Draft Mode and Parallel Thumbnail Generation]
**Learning:** Sequential filmstrip thumbnail loading using Pillow's `convert("RGB")` and `LANCZOS` resampling is a major UI bottleneck (15+ seconds for 50 4K frames). Using Pillow JPEG `draft()` mode / OpenCV `cv2.INTER_AREA` area downscaling combined with multi-threaded `ThreadPoolExecutor` speeds up thumbnail loading by ~3x-6x (~15.5s down to 5.3s for 50 4K images).
**Action:** Use fast downsampling (Pillow JPEG draft mode, OpenCV `INTER_AREA`, and `BOX` filter) with `ThreadPoolExecutor` for batch thumbnail decoding.
