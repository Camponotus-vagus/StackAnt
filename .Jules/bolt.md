
## 2025-05-15 - [Grayscale Guide for Guided Filter]
**Learning:** Using a 1-channel grayscale guide for `cv2.ximgproc.guidedFilter` is ~2x faster than a 3-channel RGB guide and sufficient for weight map smoothing in Laplacian pyramids.
**Action:** Always prefer grayscale guides for smoothing masks unless color-specific guidance is strictly required.

## 2025-05-15 - [Cumulative Fusion Loop]
**Learning:** Stacking all per-image weight maps into a single array for normalization (`np.stack`) creates a massive memory bottleneck (O(N * H * W)).
**Action:** Use cumulative accumulation (`fused += w * band`, `total_weight += w`) to reduce peak memory by ~50% in image fusion pipelines.
