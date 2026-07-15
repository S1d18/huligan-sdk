"""Fingerprint coherence / plausibility validator.

Our per-key ``.conf`` is transparent and controllable, but the compose-mode generator draws
several hardware attributes independently, so it can emit cross-attribute combinations that
don't occur on real devices (a 2-core / 2 GB box with an RTX 4090; a Win32 UA with a Metal
renderer; ``device_memory=16``). Cross-attribute consistency is the strongest modern detection
vector, so this validator flags those combinations - as hard-reject ``ERROR`` (physically
impossible / spec-violating / single-signal tell) or ``WARN`` (rare-but-real).

Pure stdlib, no dependencies: importable by the GUI, the ``huligan validate`` CLI, and doctor.
Reads existing ``.conf`` keys only - no ``CONF_SCHEMA_VERSION`` bump.

Scope: the cleanly-checkable constraints C1-C17. The optional coherent-identity device-DB mode
and the ``gpu_identity.py`` resolver (C18-C20 deep GL/WebGPU consistency) are a follow-up gated
on curated real-device data + the T2.3 browser patch.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Tuple


class Severity(IntEnum):
    INFO = 10
    WARN = 20
    ERROR = 30  # hard-reject


@dataclass(frozen=True)
class Violation:
    code: str
    severity: Severity
    message: str
    keys: Tuple[str, ...] = ()
    observed: object = None
    expected: object = None


@dataclass
class CoherenceReport:
    violations: List[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(v.severity >= Severity.ERROR for v in self.violations)

    @property
    def errors(self) -> List[Violation]:
        return [v for v in self.violations if v.severity >= Severity.ERROR]

    def raise_for_errors(self) -> None:
        if not self.ok:
            raise CoherenceError(self)


class CoherenceError(ValueError):
    def __init__(self, report: CoherenceReport):
        self.report = report
        msg = "; ".join(f"{v.code}: {v.message}" for v in report.errors)
        super().__init__(f"incoherent fingerprint: {msg}")


_VALID_DEVICE_MEMORY = {0.25, 0.5, 1, 2, 4, 8}


# --- family classifiers ---------------------------------------------------

def _platform_family(platform: Optional[str]) -> Optional[str]:
    p = platform or ""
    if p == "Win32":
        return "windows"
    if p == "MacIntel":
        return "macos"
    if p.startswith("Linux"):
        return "linux"
    return None


def _gpu_family(s: Optional[str]) -> Optional[str]:
    s = (s or "").lower()
    if "apple" in s or "metal" in s:
        return "apple"
    if "nvidia" in s or "geforce" in s or "rtx" in s or "gtx" in s:
        return "nvidia"
    if "amd" in s or "radeon" in s or re.search(r"\brx\s*\d", s):
        return "amd"
    if "intel" in s or "uhd" in s or "iris" in s:
        return "intel"
    return None


def _renderer_os_family(renderer: Optional[str]) -> Optional[str]:
    r = (renderer or "").lower()
    if "metal" in r or "apple" in r:
        return "macos"
    if "d3d11" in r or "direct3d" in r or "vs_5_0" in r or "ps_5_0" in r:
        return "windows"
    if "glx" in r or "vulkan" in r or (r.startswith("opengl") and "angle" not in r):
        return "linux"
    return None  # bare ANGLE without a backend hint is ambiguous


# --- ctx normalizers (profile and .conf share one predicate set) ----------

def _ctx_from_profile(p, binary_os: str) -> dict:
    def g(name):
        return getattr(p, name, None)
    return {
        "platform": g("platform"),
        "cpu_cores": g("cpu_cores"),
        "device_memory": g("device_memory"),
        "max_touch_points": g("max_touch_points"),
        "webgl_vendor": g("webgl_vendor"),
        "webgl_renderer": g("webgl_renderer"),
        "webgpu_vendor": g("webgpu_vendor"),
        "screen_width": g("screen_width"),
        "screen_height": g("screen_height"),
        "avail_width": g("avail_width"),
        "avail_height": g("avail_height"),
        "color_depth": g("color_depth"),
        "device_pixel_ratio": g("device_pixel_ratio"),
        "languages": g("languages"),
        "timezone": g("timezone"),
        "fonts": list(g("fonts") or []),
        "binary_os": binary_os,
    }


def _read_conf_text(text_or_path) -> str:
    if hasattr(text_or_path, "read_text"):
        return text_or_path.read_text(encoding="utf-8")
    s = str(text_or_path)
    if "\n" not in s and os.path.exists(s):
        with open(s, encoding="utf-8") as f:
            return f.read()
    return s


def _ctx_from_conf(text: str, binary_os: str) -> dict:
    d = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip()

    def _i(key):
        try:
            return int(float(d[key]))
        except Exception:
            return None

    def _f(key):
        try:
            return float(d[key])
        except Exception:
            return None

    fonts = [x.strip() for x in re.split(r"[,|]", d.get("fonts", "")) if x.strip()]
    return {
        "platform": d.get("platform"),
        "cpu_cores": _i("cpu_cores"),
        "device_memory": _f("device_memory"),
        "max_touch_points": _i("max_touch_points"),
        "webgl_vendor": d.get("webgl_vendor"),
        "webgl_renderer": d.get("webgl_renderer"),
        "webgpu_vendor": d.get("webgpu_vendor"),
        "screen_width": _i("screen_width"),
        "screen_height": _i("screen_height"),
        "avail_width": _i("screen_avail_width"),
        "avail_height": _i("screen_avail_height"),
        "color_depth": _i("color_depth"),
        "device_pixel_ratio": _f("device_pixel_ratio"),
        "languages": d.get("languages"),
        "timezone": d.get("timezone"),
        "fonts": fonts,
        "binary_os": binary_os,
    }


# --- constraint predicates (each: ctx -> Violation | None) ----------------

def _c1(ctx):
    fam = _platform_family(ctx["platform"])
    if fam and fam != ctx["binary_os"]:
        return Violation("C1_platform_vs_binary_os", Severity.ERROR,
                         f"platform {ctx['platform']!r} (OS {fam}) mismatches the target binary "
                         f"OS ({ctx['binary_os']}); the UA-string OS token is fixed by the build, "
                         "so this is a UA-vs-UA-CH cross-check failure",
                         ("platform",), ctx["platform"], f"OS family == {ctx['binary_os']}")


def _c2(ctx):
    pf, rf = _platform_family(ctx["platform"]), _renderer_os_family(ctx["webgl_renderer"])
    if pf and rf and pf != rf:
        return Violation("C2_renderer_vs_platform", Severity.ERROR,
                         f"webgl_renderer OS/API family ({rf}) mismatches platform ({pf})",
                         ("webgl_renderer", "platform"), ctx["webgl_renderer"], f"family == {pf}")


def _c3(ctx):
    gf = _gpu_family(ctx["webgl_vendor"]) or _gpu_family(ctx["webgl_renderer"])
    wf = _gpu_family(ctx["webgpu_vendor"])
    if gf and wf and gf != wf:
        return Violation("C3_webgpu_vs_webgl_vendor", Severity.ERROR,
                         f"webgpu_vendor family ({wf}) mismatches webgl vendor family ({gf}); "
                         "the same physical GPU drives both APIs",
                         ("webgpu_vendor", "webgl_vendor"), ctx["webgpu_vendor"], f"family == {gf}")


def _c4(ctx):
    if ctx["platform"] == "MacIntel" and (ctx["max_touch_points"] or 0) != 0:
        return Violation("C4_mac_touch_points", Severity.ERROR,
                         f"MacIntel with max_touch_points={ctx['max_touch_points']}; macOS exposes 0 "
                         "(no touchscreen Macs)", ("max_touch_points", "platform"),
                         ctx["max_touch_points"], 0)


def _c5(ctx):
    m = ctx["device_memory"]
    if m is not None and m not in _VALID_DEVICE_MEMORY:
        return Violation("C5_device_memory_cap", Severity.ERROR,
                         f"device_memory={m} is impossible; navigator.deviceMemory reports only "
                         "{0.25,0.5,1,2,4,8}", ("device_memory",), m, sorted(_VALID_DEVICE_MEMORY))


def _c6(ctx):
    c = ctx["cpu_cores"]
    if c is None:
        return None
    if c < 1 or c > 128 or c in (3, 5, 7):
        return Violation("C6_cpu_cores", Severity.ERROR,
                         f"cpu_cores={c} is not a real logical-core count",
                         ("cpu_cores",), c, "2-128, no small odd primes")


def _c8(ctx):
    r = (ctx["webgl_renderer"] or "").lower()
    flagship = bool(re.search(r"rtx\s*(40|50)\d\d|rx\s*79\d\d", r))
    if flagship and ((ctx["cpu_cores"] or 99) < 6 or (ctx["device_memory"] or 99) < 8):
        return Violation("C8_flagship_gpu_low_spec", Severity.WARN,
                         f"flagship discrete GPU with cpu_cores={ctx['cpu_cores']} / "
                         f"device_memory={ctx['device_memory']} - implausible pairing",
                         ("webgl_renderer", "cpu_cores", "device_memory"), None, "cores>=6 and mem>=8")


def _c10(ctx):
    c, m = ctx["cpu_cores"], ctx["device_memory"]
    if c and m and m * 2 < c:
        return Violation("C10_ram_cores_band", Severity.WARN,
                         f"device_memory={m} GB is low for {c} cores",
                         ("device_memory", "cpu_cores"), (m, c), "device_memory >= cores/2")


def _c11(ctx):
    w, h, aw, ah = (ctx["screen_width"], ctx["screen_height"],
                    ctx["avail_width"], ctx["avail_height"])
    if None in (w, h, aw, ah):
        return None
    if aw > w or ah > h:
        return Violation("C11_avail_bounds", Severity.ERROR,
                         f"available screen ({aw}x{ah}) exceeds the panel ({w}x{h})",
                         ("screen_avail_width", "screen_avail_height"), (aw, ah), "<= panel")


def _c14(ctx):
    cd = ctx["color_depth"]
    if cd is not None and cd != 24:
        return Violation("C14_color_depth", Severity.INFO,
                         f"color_depth={cd}; desktop Chrome is effectively always 24",
                         ("color_depth",), cd, 24)


def _c15(ctx):
    primary = ((ctx["languages"] or "").lower().split(",")[0]).strip()
    fonts = " ".join(ctx["fonts"]).lower()
    need = None
    if primary.startswith("ja"):
        need = ["gothic", "meiryo", "yu ", "mincho", "hiragino"]
    elif primary.startswith("ko"):
        need = ["gulim", "malgun", "batang", "dotum", "gothic"]
    elif primary.startswith("zh"):
        need = ["simsun", "simhei", "yahei", "pingfang", "heiti", "song"]
    if need and ctx["fonts"] and not any(n in fonts for n in need):
        return Violation("C15_locale_fonts", Severity.WARN,
                         f"primary language {primary!r} but no matching script fonts in the list",
                         ("languages", "fonts"), primary, "CJK fonts present for CJK locale")


def _c17(ctx):
    fonts = " ".join(ctx["fonts"]).lower()
    if ctx["platform"] == "MacIntel" and "segoe ui" in fonts:
        return Violation("C17_platform_fonts", Severity.WARN,
                         "MacIntel profile carries Windows-only 'Segoe UI'",
                         ("fonts", "platform"), "Segoe UI", "platform-matched fonts")


_PREDICATES = [_c1, _c2, _c3, _c4, _c5, _c6, _c8, _c10, _c11, _c14, _c15, _c17]


def _run(ctx) -> CoherenceReport:
    violations = []
    for pred in _PREDICATES:
        try:
            v = pred(ctx)
        except Exception:
            v = None
        if v is not None:
            violations.append(v)
    return CoherenceReport(violations=violations)


# --- public entry points --------------------------------------------------

def validate_profile(profile, *, binary_os: str = "windows") -> CoherenceReport:
    """Validate a :class:`huligan.FingerprintProfile` for cross-attribute coherence."""
    return _run(_ctx_from_profile(profile, binary_os))


def validate_conf(text_or_path, *, binary_os: str = "windows") -> CoherenceReport:
    """Validate a ``.conf`` (path, ``Path``, or text) for cross-attribute coherence."""
    return _run(_ctx_from_conf(_read_conf_text(text_or_path), binary_os))
