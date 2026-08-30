"""Tests for the fingerprint coherence validator (T3.2)."""
import huligan
from huligan import validate_conf, validate_profile
from huligan.fingerprint import FingerprintProfile

# Import rather than duplicate: a local copy here silently re-encoded the old
# {0.25..8} ceiling after C5 was corrected to the real desktop set {2,4,8,16,32}.
from huligan.coherence import _VALID_DEVICE_MEMORY as _VALID_MEM


def _conf(**over):
    base = dict(
        platform="Win32", cpu_cores=8, device_memory=8, max_touch_points=0,
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x2503) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        webgpu_vendor="nvidia",
        screen_width=1920, screen_height=1080, screen_avail_width=1920, screen_avail_height=1040,
        color_depth=24, device_pixel_ratio="1.0", languages="en-US,en",
    )
    base.update(over)
    return "\n".join(f"{k}={v}" for k, v in base.items())


def _codes(report):
    return {v.code for v in report.violations}


def test_coherent_conf_is_ok():
    r = validate_conf(_conf())
    assert r.ok, [v.code for v in r.errors]


def test_device_memory_cap_c5():
    """navigator.deviceMemory on DESKTOP is a power of two clamped to [2,32].

    This test used to assert that 16 was impossible, encoding the old
    {0.25..8} spec text. Measured against stock Chrome 152 on a 64-core box:
    deviceMemory reported 32. approximated_device_memory.cc (identical in 151
    and 152) clamps desktop to kMinMemory=2.0 / kMaxMemory=32.0 and keeps the
    8 GB ceiling only under BUILDFLAG(IS_ANDROID).
    """
    # legal on desktop, and 16 GB is one of the most common configurations
    assert validate_conf(_conf(device_memory=16)).ok
    assert validate_conf(_conf(device_memory=32)).ok

    # above the desktop clamp
    r = validate_conf(_conf(device_memory=64))
    assert not r.ok and "C5_device_memory_cap" in _codes(r)

    # below it (the old sub-2 values are Android-only)
    r = validate_conf(_conf(device_memory=1))
    assert not r.ok and "C5_device_memory_cap" in _codes(r)

    # not a power of two
    r = validate_conf(_conf(device_memory=12))
    assert not r.ok and "C5_device_memory_cap" in _codes(r)


def test_mac_touch_points_c4():
    r = validate_conf(_conf(
        platform="MacIntel", max_touch_points=10,
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
        webgpu_vendor="apple"), binary_os="macos")
    assert "C4_mac_touch_points" in _codes(r) and not r.ok


def test_platform_vs_binary_os_c1():
    r = validate_conf(_conf(
        platform="MacIntel", max_touch_points=0,
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
        webgpu_vendor="apple"), binary_os="windows")
    assert "C1_platform_vs_binary_os" in _codes(r) and not r.ok


def test_renderer_vs_platform_c2():
    r = validate_conf(_conf(
        webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)"))
    assert "C2_renderer_vs_platform" in _codes(r) and not r.ok


def test_webgpu_vs_webgl_vendor_c3():
    r = validate_conf(_conf(webgpu_vendor="amd"))
    assert "C3_webgpu_vs_webgl_vendor" in _codes(r) and not r.ok


def test_avail_bounds_c11():
    r = validate_conf(_conf(screen_avail_height=1200))
    assert "C11_avail_bounds" in _codes(r) and not r.ok


def test_cpu_cores_c6():
    r = validate_conf(_conf(cpu_cores=7))
    assert "C6_cpu_cores" in _codes(r) and not r.ok


def test_all_templates_are_coherent():
    """Every shipped template must be spec-legal device_memory (the L6 fix holds)."""
    from huligan import templates
    for name, t in templates.TEMPLATES.items():
        dm = t["overrides"].get("device_memory")
        assert dm in _VALID_MEM, f"{name}: device_memory={dm} violates C5"


def test_from_seed_win32_profiles_have_no_errors():
    """A fresh compose-mode profile must validate with no ERROR on the Win32 build."""
    for seed in range(0, 40):
        p = FingerprintProfile.from_seed(seed)
        if getattr(p, "platform", None) != "Win32":
            continue  # non-Win32 is C1-incoherent on the win64 binary by design (L4)
        r = validate_profile(p)
        assert not r.errors, f"seed {seed}: {[v.code for v in r.errors]}"


def test_exports():
    for n in ("validate_profile", "validate_conf", "CoherenceReport",
              "Violation", "Severity", "CoherenceError"):
        assert hasattr(huligan, n), n


def test_cpu_tier_port_matches_chromium_unittest():
    """Our GetTierFromCores port must match Chromium's own unittest table.

    Source of truth: content/browser/cpu_performance/cpu_performance_unittest.cc
    TEST_F(CpuPerformanceTest, GetTierFromCores) in the Chrome 152 tree. If a
    future major re-bands the tiers, this fails instead of silently emitting a
    tier that contradicts our own hardwareConcurrency.
    """
    from huligan.fingerprint import cpu_tier_from_cores

    chromium_table = {
        1: 1, 2: 1,            # kLow
        3: 2, 4: 2,            # kMid
        5: 3, 8: 3, 12: 3,     # kHigh
        13: 4, 16: 4, 96: 4,   # kUltra
        0: 0, -42: 0,          # kUnknown
    }
    for cores, tier in chromium_table.items():
        assert cpu_tier_from_cores(cores) == tier, "cores=%d" % cores


def test_cpu_tier_vs_cores_c23():
    # 8 cores lands in the 5..12 band -> kHigh (3)
    assert validate_conf(_conf(cpu_cores=8, cpu_performance_tier=3)).ok

    # tier 4 would need >=13 cores
    r = validate_conf(_conf(cpu_cores=8, cpu_performance_tier=4))
    assert not r.ok and "C23_cpu_tier_vs_cores" in _codes(r)

    # 0 = kUnknown is always legal ("not reported")
    assert validate_conf(_conf(cpu_cores=8, cpu_performance_tier=0)).ok
