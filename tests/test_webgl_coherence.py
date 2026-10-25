"""WebGL fingerprint coherence guard.

Codifies the ground truth established 2026-07 from real captures - native NVIDIA V100/1650/660 -
corrected 2026-10: the WebGL numeric getParameter surface is an ANGLE-D3D11 constant per VENDOR, not
global. The 2026-07 "6 Intel/AMD Dolphin captures" were NVIDIA-host numbers under a spoofed renderer
string. ANGLE enables skipVSConstantRegisterZero for NVIDIA only (renderer11_utils.cpp), so NVIDIA
reports 36347=4095 / 35658=16380 / 35377=212988 and Intel/AMD/WARP 4096 / 16384 / 212992. The NVIDIA
numbers under an Intel renderer made CreepJS flag "suspicious gpu" on 155. These asserts would have caught every value bug fixed in this pass
(34076/3379/34024 doubled-16384; integrated 35657=2048; integrated viewport [16384,16384]) and
block their return on future Chrome upgrades.
"""
import pytest

from huligan.data.gpu_identity import GL_PARAMS_NATIVE
from huligan.data.webgl_profiles import (
    FINGERPRINT_PARAMS, GL_ENUM_NAMES, WEBGL2_PARAMS_BY_GPU, get_fingerprint_params)

# Canonical GL enum names for every emitted param (verified against Khronos enum values).
CANONICAL_NAMES = {
    3379: "MAX_TEXTURE_SIZE",
    3386: "MAX_VIEWPORT_DIMS",
    33901: "ALIASED_POINT_SIZE_RANGE",
    33902: "ALIASED_LINE_WIDTH_RANGE",
    34024: "MAX_RENDERBUFFER_SIZE",
    34076: "MAX_CUBE_MAP_TEXTURE_SIZE",
    34921: "MAX_VERTEX_ATTRIBS",
    34930: "MAX_TEXTURE_IMAGE_UNITS",
    35657: "MAX_FRAGMENT_UNIFORM_COMPONENTS",
    35658: "MAX_VERTEX_UNIFORM_COMPONENTS",
    35659: "MAX_VARYING_COMPONENTS",
    35660: "MAX_VERTEX_TEXTURE_IMAGE_UNITS",
    35661: "MAX_COMBINED_TEXTURE_IMAGE_UNITS",
    36347: "MAX_VERTEX_UNIFORM_VECTORS",
    36348: "MAX_VARYING_VECTORS",
    36349: "MAX_FRAGMENT_UNIFORM_VECTORS",
    37154: "MAX_VERTEX_OUTPUT_COMPONENTS",
    37157: "MAX_FRAGMENT_INPUT_COMPONENTS",
}

# The confirmed ANGLE-D3D11 constant values for NVIDIA (real captures; identical across tiers).
CONFIRMED = {
    3379: 16384, 34024: 16384, 34076: 16384,
    3386: [32767, 32767],
    33901: [1, 1024], 33902: [1, 1],
    34921: 16, 34930: 16, 35660: 16, 35661: 32,
    35657: 4096, 35658: 16380, 35659: 120,
    36347: 4095, 36348: 30, 36349: 1024,
    37154: 120, 37157: 120,
}
# Intel/AMD: no reserved vertex uniform vector (skipVSConstantRegisterZero is NVIDIA-only).
CONFIRMED_NON_NVIDIA = {**CONFIRMED, 35658: 16384, 36347: 4096}
# Derived int64 WebGL2 params: 12 uniform blocks * 16384 + per-stage default-block components.
COMBINED = {"nvidia": {35377: 212988, 35379: 200704}, "other": {35377: 212992, 35379: 200704}}


def _confirmed_for(label):
    return CONFIRMED if label.startswith("nvidia") else CONFIRMED_NON_NVIDIA

# Real renderer strings that must all resolve to the same constant set.
RENDERERS = {
    "nvidia": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 (0x00002484) Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "intel_integrated": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "amd_discrete": "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "amd_integrated": "ANGLE (AMD, AMD Radeon RX Vega 11 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
}


def _norm(v):
    return list(v) if isinstance(v, (list, tuple)) else v


def test_webgl2_classes_identical_within_vendor():
    """WebGL numeric params are D3D11 constants - classes of one vendor must be byte-identical."""
    for vendor in ("nvidia", "intel", "amd"):
        classes = {n: p for n, p in WEBGL2_PARAMS_BY_GPU.items() if n.startswith(vendor)}
        _assert_identical(classes)


def test_intel_amd_share_values():
    """Intel and AMD differ from NVIDIA only by the reserved register - never from each other."""
    _assert_identical({n: p for n, p in WEBGL2_PARAMS_BY_GPU.items() if not n.startswith("nvidia")})


def _assert_identical(classes):
    ref_name, ref = next(iter(classes.items()))
    for name, params in classes.items():
        diff = {e: (_norm(ref.get(e)), _norm(params.get(e)))
                for e in set(ref) | set(params) if _norm(ref.get(e)) != _norm(params.get(e))}
        assert not diff, f"{name} differs from {ref_name}: {diff} (must be identical - per-class variation is a tell)"


def test_no_impossible_d3d11_caps():
    """Texture-family caps are 16384 on D3D11 FL11 (32768 = the doubled-16384 bug); viewport = 32767."""
    for name, params in WEBGL2_PARAMS_BY_GPU.items():
        for enum in (3379, 34024, 34076):
            assert params[enum] == 16384, f"{name} enum {enum} = {params[enum]} (D3D11 max is 16384, not 32768)"
        assert _norm(params[3386]) == [32767, 32767], f"{name} viewport = {params[3386]}, must be [32767,32767]"


def test_internal_coherence():
    """COMPONENTS == VECTORS*4 is a hard GL-spec invariant (the 35657=2048 bug violated it)."""
    for name, params in WEBGL2_PARAMS_BY_GPU.items():
        assert params[35657] == params[36349] * 4, f"{name}: fragment components != vectors*4"
        assert params[35658] == params[36347] * 4, f"{name}: vertex components != vectors*4"


def test_classes_match_confirmed_constants():
    for name, params in WEBGL2_PARAMS_BY_GPU.items():
        for enum, want in _confirmed_for(name).items():
            assert _norm(params.get(enum)) == _norm(want), \
                f"{name} enum {enum} ({GL_ENUM_NAMES.get(enum)}) = {params.get(enum)}, expected {want}"


@pytest.mark.parametrize("label,renderer", list(RENDERERS.items()))
def test_get_fingerprint_params_matches_reality(label, renderer):
    fp = get_fingerprint_params(renderer)
    want = {**_confirmed_for(label), **COMBINED["nvidia" if label.startswith("nvidia") else "other"]}
    bad = {e: (fp.get(e), w) for e, w in want.items() if _norm(fp.get(e)) != _norm(w)}
    assert not bad, f"{label} output mismatches the real capture: {bad}"


def test_matches_gl_params_native():
    real = {int(k): v for k, v in GL_PARAMS_NATIVE.get("nvidia", {}).items()}
    fp = get_fingerprint_params(RENDERERS["nvidia"])
    bad = {e: (real[e], fp.get(e)) for e in set(real) & set(fp) if _norm(real[e]) != _norm(fp.get(e))}
    assert not bad, f"nvidia output mismatches GL_PARAMS_NATIVE ground truth: {bad}"


def test_emitted_enums_labelled_canonically():
    wrong = {e: (GL_ENUM_NAMES.get(e), name) for e, name in CANONICAL_NAMES.items()
             if GL_ENUM_NAMES.get(e) != name}
    assert not wrong, f"GL_ENUM_NAMES mislabels emitted enums (got, expected): {wrong}"


def test_every_emitted_enum_is_covered():
    """No emitted enum is missing a canonical name or confirmed value (catches new emits on upgrade)."""
    for enum in FINGERPRINT_PARAMS:
        assert enum in CANONICAL_NAMES, f"emitted enum {enum} lacks a canonical name in this guard"
        assert enum in CONFIRMED, f"emitted enum {enum} lacks a confirmed value in this guard"
