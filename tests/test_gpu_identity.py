"""Tests for the GPU identity resolver (T2.3 prep) - the verifiable logic slice."""
import pytest

from huligan.data import gpu_identity as gi
from huligan.data.webgl_profiles import classify_gpu

_RTX3060 = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002503) Direct3D11 vs_5_0 ps_5_0, D3D11)"
_RTX4090 = "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 (0x00002684) Direct3D11 vs_5_0 ps_5_0, D3D11)"
_RX7900 = "ANGLE (AMD, AMD Radeon RX 7900 XTX Direct3D11 vs_5_0 ps_5_0, D3D11)"
_VEGA = "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"
_UHD = "ANGLE (Intel, Intel(R) UHD Graphics 770 (0x00004680) Direct3D11 vs_5_0 ps_5_0, D3D11)"
_APPLE = "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)"


def test_classify_windows_classes():
    R = gi.resolve_gpu_identity
    assert R("Google Inc. (NVIDIA)", _RTX4090, os_family="windows").gpu_class == "nvidia_high"
    assert R("Google Inc. (NVIDIA)", _RTX3060, os_family="windows").gpu_class == "nvidia_mid"
    assert R("Google Inc. (AMD)", _RX7900, os_family="windows").gpu_class == "amd_discrete"
    assert R("Google Inc. (AMD)", _VEGA, os_family="windows").gpu_class == "amd_integrated"
    assert R("Google Inc. (Intel)", _UHD, os_family="windows").gpu_class == "intel_integrated"


def test_apple_class_fixes_l5():
    # The bug: classify_gpu returns nvidia_mid for an Apple/Metal renderer.
    assert classify_gpu(_APPLE) == "nvidia_mid"
    # The fix: resolve_gpu_identity returns the explicit 'apple' class instead.
    ident = gi.resolve_gpu_identity("Google Inc. (Apple)", _APPLE, os_family="macos")
    assert ident.gpu_class == "apple"
    assert ident.api_backend == "metal"


def test_backend_by_os():
    assert gi.resolve_gpu_identity("x", _RTX3060, os_family="windows").api_backend == "d3d11"
    assert gi.resolve_gpu_identity("x", _RTX3060, os_family="linux").api_backend == "opengl"


def test_device_id_extracted():
    ident = gi.resolve_gpu_identity("Google Inc. (NVIDIA)", _RTX3060, os_family="windows")
    assert ident.device_id == "0x00002503"


def test_gl_params_for_windows_populated():
    ident = gi.resolve_gpu_identity("Google Inc. (NVIDIA)", _RTX3060, os_family="windows")
    gl = gi.gl_params_for(ident)
    assert gl.webgl1_params and gl.webgl2_params
    assert gl.webgl2_extensions


def test_gl_params_for_apple_raises_not_guesses():
    # L5: never silently return nvidia_mid params for Apple; force explicit handling.
    ident = gi.resolve_gpu_identity("Google Inc. (Apple)", _APPLE, os_family="macos")
    with pytest.raises(gi.GpuDataUnavailable):
        gi.gl_params_for(ident)


def test_webgpu_adapter_total_over_all_classes():
    for renderer, vendor, osf in [(_RTX4090, "NVIDIA", "windows"), (_RX7900, "AMD", "windows"),
                                  (_UHD, "Intel", "windows"), (_APPLE, "Apple", "macos")]:
        a = gi.webgpu_adapter_for(gi.resolve_gpu_identity(vendor, renderer, os_family=osf))
        assert a.limits and a.limits["maxBufferSize"] > 0
        assert a.subgroup_max_size >= a.subgroup_min_size > 0
        assert a.vendor in ("nvidia", "amd", "intel", "apple")


def test_webgpu_arch():
    R = gi.resolve_gpu_identity
    assert gi.webgpu_adapter_for(R("NVIDIA", _RTX4090, os_family="windows")).architecture == "ampere"
    assert gi.webgpu_adapter_for(R("Apple", _APPLE, os_family="macos")).architecture == "apple-silicon"
    assert gi.webgpu_adapter_for(R("AMD", _RX7900, os_family="windows")).architecture == "rdna3"


def test_webgpu_limits_are_native_not_dolphin_clamped():
    # Native Chrome (GTX 1060 capture) reports 16384/2048/48; Dolphin Anty CLAMPS to 8192/256/16
    # (a tell). We present the native set, same across GPU classes (D3D11-feature-level driven).
    a_nv = gi.webgpu_adapter_for(gi.resolve_gpu_identity("NVIDIA", _RTX4090, os_family="windows"))
    a_amd = gi.webgpu_adapter_for(gi.resolve_gpu_identity("AMD", _VEGA, os_family="windows"))
    assert a_nv.limits == a_amd.limits
    L = a_nv.limits
    assert L["maxTextureDimension2D"] == 16384           # native (Dolphin clamps to 8192)
    assert L["maxTextureArrayLayers"] == 2048            # native (Dolphin clamps to 256)
    assert L["maxSampledTexturesPerShaderStage"] == 48   # native (Dolphin clamps to 16)
    assert L["maxBufferSize"] == 2147483648


def test_gl_params_native_ground_truth():
    # Real captured NVIDIA WebGL2 params - byte-identical across native V100/1650/660 + Dolphin.
    nv = gi.GL_PARAMS_NATIVE["nvidia"]
    assert nv[3379] == 16384            # MAX_TEXTURE_SIZE
    assert nv[34076] == 16384           # MAX_CUBE_MAP (webgl_profiles has 32768 in a class = bug)
    assert nv[34047] == 16              # MAX_TEXTURE_MAX_ANISOTROPY_EXT
    assert nv[36347] == 4095            # MAX_VERTEX_UNIFORM_VECTORS
    assert nv[3386] == [32767, 32767]   # MAX_VIEWPORT_DIMS
