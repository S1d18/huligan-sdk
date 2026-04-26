"""Fingerprint randomization data sources"""

from .gpu_vendors import get_random_gpu, NVIDIA_GPUS, AMD_GPUS, INTEL_GPUS
from .screen_resolutions import get_random_resolution, COMMON_RESOLUTIONS
from .font_lists import (
    get_random_fonts,
    CORE_WINDOWS_FONTS,
    STANDARD_WINDOWS_FONTS,
    MACOS_FONTS,
    LINUX_FONTS,
)
from .webgl_profiles import (
    get_fingerprint_params,
    get_extensions,
    classify_gpu,
    SHADER_PRECISION_D3D11,
    FINGERPRINT_PARAMS,
)

__all__ = [
    "get_random_gpu",
    "get_random_resolution",
    "get_random_fonts",
    "get_fingerprint_params",
    "get_extensions",
    "classify_gpu",
    "NVIDIA_GPUS",
    "AMD_GPUS",
    "INTEL_GPUS",
    "COMMON_RESOLUTIONS",
    "CORE_WINDOWS_FONTS",
    "STANDARD_WINDOWS_FONTS",
    "MACOS_FONTS",
    "LINUX_FONTS",
    "SHADER_PRECISION_D3D11",
    "FINGERPRINT_PARAMS",
]
