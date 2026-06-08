"""Default parameters and constants for StackAnt."""
import platform

APP_NAME = "StackAnt"
APP_VERSION = "0.1.0.dev0"
ORG_NAME = "StackAnt"

FFMPEG_DEFAULT_FORMAT = "tiff"
FRAME_TARGET_COUNT = 75
LAPLACIAN_THRESHOLD_AUTO = True
FOCUS_STACK_CONSISTENCY = 2
FOCUS_STACK_DENOISE = True
FOCUS_STACK_SHARP_STRENGTH = 1
# macOS' OpenCL is deprecated and focus-stack's GPU wavelet kernel is unreliable
# there, so default to CPU on a fresh install. Linux/Windows keep GPU (False).
FOCUS_STACK_NO_OPENCL_DEFAULT = platform.system() == "Darwin"
JPEG_DEFAULT_QUALITY = 95
PREVIEW_MAX_PX = 800
