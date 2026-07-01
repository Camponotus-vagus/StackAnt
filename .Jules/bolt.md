
## 2025-05-15 - [Grayscale Guide for Guided Filter]
**Learning:** Using a 1-channel grayscale guide for `cv2.ximgproc.guidedFilter` is ~2x faster than a 3-channel RGB guide and sufficient for weight map smoothing in Laplacian pyramids.
**Action:** Always prefer grayscale guides for smoothing masks unless color-specific guidance is strictly required.

## 2025-05-15 - [Cumulative Fusion Loop]
**Learning:** Stacking all per-image weight maps into a single array for normalization (`np.stack`) creates a massive memory bottleneck (O(N * H * W)).
**Action:** Use cumulative accumulation (`fused += w * band`, `total_weight += w`) to reduce peak memory by ~50% in image fusion pipelines.

## 2025-05-15 - [Streaming and Parallel Alignment]
**Learning:** Loading all input frames into memory before processing is a significant memory bottleneck for large focus stacks. Using a generator-based stream and parallelizing the alignment step with `ThreadPoolExecutor` allows for O(1) frame memory overhead and faster execution.
**Action:** Stream heavy image data through generators and use parallel executors for independent CPU-bound image processing tasks like alignment.
