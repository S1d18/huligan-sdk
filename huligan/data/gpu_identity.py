"""GPU identity resolver - single source of truth for GPU-coherent GL / WebGPU values.

Unifies the scattered helpers (``classify_gpu``, ``get_webgl_params`` / ``get_fingerprint_params``,
``get_extensions``, and the inline WebGPU vendor/arch heuristic in ``fingerprint.py:527-538``)
behind one resolver, and adds the explicit ``"apple"`` class that ``classify_gpu`` silently
swallows into ``"nvidia_mid"`` today (audit finding L5). Consumed by the T2.3 emitter and by the
T3.2 validator's C18-C20 so "what we emit" and "what we validate" can never drift.

PREP STATUS (T2.3, verifiable slice):
  * Classification (incl. the Apple fix), ``gl_params_for``, and ``webgpu_adapter_for`` STRUCTURE
    are complete + unit-tested here.
  * ``gl_params_for`` WRAPS the shipping ``webgl_profiles`` data - NO fingerprint-output change.
  * ``WEBGPU_LIMITS_BY_CLASS`` holds REFERENCE values (WebGPU-spec-informed). They MUST be replaced
    with real ``navigator.gpu.requestAdapter().limits`` captures on the build box before the emitter
    is wired to them (a wrong limit is a tell). Capture recipe in ``WEBGPU_LIMIT_CAPTURE_JS`` below.
  * This module is NOT yet wired into ``fingerprint.py`` output - wiring changes the fingerprint and
    needs operator BrowserScan/CreepJS validation (see huligan-browser/docs/CLOAKBROWSER_T2x_REBUILD_PLAN.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from .webgl_profiles import classify_gpu, get_extensions, get_webgl_params

# Run this in a real Chrome console per GPU class to capture authoritative limits:
#   copy(JSON.stringify(Object.fromEntries(
#     [...Object.entries((await navigator.gpu.requestAdapter()).limits)])))
WEBGPU_LIMIT_CAPTURE_JS = (
    "JSON.stringify(Object.fromEntries("
    "[...Object.entries((await navigator.gpu.requestAdapter()).limits)]))"
)


class GpuDataUnavailable(NotImplementedError):
    """A known GPU class has no captured data yet (e.g. Apple GL params - Mac support deferred)."""


@dataclass(frozen=True)
class GpuIdentity:
    vendor_string: str      # webgl_vendor / GL_VENDOR
    renderer_string: str    # webgl_renderer / GL_RENDERER (full ANGLE/Metal string)
    device_id: str          # PCI id (0x....) or the chip/model
    gpu_class: str          # nvidia_high|nvidia_mid|amd_discrete|amd_integrated|
                            #  intel_integrated|intel_discrete|apple
    os_family: str          # windows|macos|linux
    api_backend: str        # d3d11|metal|opengl


@dataclass(frozen=True)
class GlParamSet:
    webgl1_params: Dict[int, object]
    webgl2_params: Dict[int, object]
    webgl1_extensions: List[str]
    webgl2_extensions: List[str]


@dataclass(frozen=True)
class WebGpuAdapter:
    vendor: str
    architecture: str
    device: str
    description: str
    limits: Dict[str, int]
    features: List[str]
    subgroup_min_size: int
    subgroup_max_size: int


_BACKEND_BY_OS = {"windows": "d3d11", "macos": "metal", "linux": "opengl"}
_WEBGPU_VENDOR_BY_CLASS = {
    "nvidia_high": "nvidia", "nvidia_mid": "nvidia",
    "amd_discrete": "amd", "amd_integrated": "amd",
    "intel_integrated": "intel", "intel_discrete": "intel",
    "apple": "apple",
}
_SUBGROUP_BY_CLASS = {
    "nvidia_high": (32, 32), "nvidia_mid": (32, 32),
    "amd_discrete": (32, 64), "amd_integrated": (32, 64),
    "intel_integrated": (8, 32), "intel_discrete": (8, 32),
    "apple": (32, 32),
}
_FEATURES_COMMON = ["depth-clip-control", "depth32float-stencil8",
                    "texture-compression-bc", "indirect-first-instance",
                    "rg11b10ufloat-renderable"]

# REFERENCE values only (WebGPU-spec-informed, >= spec guaranteed minimums). VERIFY per class
# against real captures (WEBGPU_LIMIT_CAPTURE_JS) before wiring into emitter output.
_DISCRETE = {"maxBufferSize": 4294967296, "maxStorageBufferBindingSize": 2147483644,
             "maxComputeWorkgroupSizeX": 1024, "maxComputeWorkgroupSizeY": 1024,
             "maxComputeWorkgroupSizeZ": 64, "maxComputeInvocationsPerWorkgroup": 1024}
_INTEGRATED = {"maxBufferSize": 2147483648, "maxStorageBufferBindingSize": 2147483644,
               "maxComputeWorkgroupSizeX": 1024, "maxComputeWorkgroupSizeY": 1024,
               "maxComputeWorkgroupSizeZ": 64, "maxComputeInvocationsPerWorkgroup": 1024}
WEBGPU_LIMITS_BY_CLASS = {
    "nvidia_high": dict(_DISCRETE),
    "nvidia_mid": dict(_DISCRETE),
    "amd_discrete": dict(_DISCRETE),
    "amd_integrated": dict(_INTEGRATED),
    "intel_integrated": dict(_INTEGRATED),
    "intel_discrete": dict(_DISCRETE),
    "apple": {"maxBufferSize": 4294967296, "maxStorageBufferBindingSize": 4294967292,
              "maxComputeWorkgroupSizeX": 1024, "maxComputeWorkgroupSizeY": 1024,
              "maxComputeWorkgroupSizeZ": 64, "maxComputeInvocationsPerWorkgroup": 1024},
}


def _is_apple(renderer: str, vendor: str) -> bool:
    s = f"{renderer} {vendor}".lower()
    return "apple" in s or "metal" in s


def _arch_for(gpu_class: str, renderer: str) -> str:
    r = renderer.upper()
    if gpu_class == "apple":
        return "apple-silicon"
    if gpu_class.startswith("nvidia"):
        return "ampere" if ("RTX 40" in r or "RTX 30" in r) else "turing"
    if gpu_class.startswith("amd"):
        return "rdna3" if "RX 7" in r else "rdna2"
    return "xe"  # intel


def resolve_gpu_identity(vendor: str, renderer: str, *, os_family: str) -> GpuIdentity:
    """Classify (vendor, renderer) into a coherent GpuIdentity.

    Adds the explicit ``"apple"`` class (L5 fix) instead of ``classify_gpu``'s silent
    ``"nvidia_mid"`` fallthrough for Metal/Apple renderers.
    """
    gpu_class = "apple" if _is_apple(renderer, vendor) else classify_gpu(renderer)
    backend = _BACKEND_BY_OS.get(os_family, "d3d11")
    m = re.search(r"0x[0-9A-Fa-f]{4,}", renderer)
    device_id = m.group(0) if m else renderer
    return GpuIdentity(vendor_string=vendor, renderer_string=renderer, device_id=device_id,
                       gpu_class=gpu_class, os_family=os_family, api_backend=backend)


def gl_params_for(identity: GpuIdentity) -> GlParamSet:
    """GL params/extensions for the identity. Wraps the shipping ``webgl_profiles`` data for the six
    Windows GPU classes; raises :class:`GpuDataUnavailable` for ``"apple"`` (Mac GL data not captured
    - Mac support deferred). Never silently guesses (that was the L5 bug)."""
    if identity.gpu_class == "apple":
        raise GpuDataUnavailable(
            "Apple GL params are not captured (Mac support deferred; see CLOAKBROWSER_T2x_REBUILD_PLAN). "
            "resolve_gpu_identity now correctly returns 'apple' instead of the old silent nvidia_mid guess."
        )
    r = identity.renderer_string
    return GlParamSet(
        webgl1_params=get_webgl_params(r, webgl_version=1),
        webgl2_params=get_webgl_params(r, webgl_version=2),
        webgl1_extensions=get_extensions(r, webgl_version=1),
        webgl2_extensions=get_extensions(r, webgl_version=2),
    )


def webgpu_adapter_for(identity: GpuIdentity) -> WebGpuAdapter:
    """WebGPU adapter (vendor/arch/device/limits/features) for the identity.

    Limits come from the REFERENCE ``WEBGPU_LIMITS_BY_CLASS`` table - replace with real captures
    before wiring the emitter. Total over every known class; raises on an unknown class.
    """
    cls = identity.gpu_class
    if cls not in WEBGPU_LIMITS_BY_CLASS:
        raise GpuDataUnavailable(f"no WebGPU adapter data for GPU class {cls!r}")
    smin, smax = _SUBGROUP_BY_CLASS[cls]
    return WebGpuAdapter(
        vendor=_WEBGPU_VENDOR_BY_CLASS[cls],
        architecture=_arch_for(cls, identity.renderer_string),
        device=identity.device_id,
        description=identity.renderer_string,
        limits=dict(WEBGPU_LIMITS_BY_CLASS[cls]),
        features=list(_FEATURES_COMMON),
        subgroup_min_size=smin,
        subgroup_max_size=smax,
    )
