"""``huligan doctor`` - consolidated self-check.

Runs green (OK) / yellow (WARN) / red (FAIL) checks over the install: patched
Chrome binary, launch smoke-test, GeoIP module + local DB, bundled fonts,
version/channel, and optional-dependency availability. ``--json`` gives a
machine-readable projection; ``--quick`` skips the launch smoke-test and any
network check.

Kept out of :mod:`huligan.__main__` so the CLI stays a thin formatter. No new
runtime dependency: colours are hand-rolled ANSI, and ``importlib.metadata`` /
``importlib.util`` / ``urllib`` are stdlib. Every check is wrapped so a broken
install degrades to WARN/FAIL rather than crashing the command.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import installer
from .conf_spec import CONF_SCHEMA_VERSION
from .version import BUILD_NUMBER, CHROME_VERSION

# ok < warn < fail for "overall"; "skipped" never counts toward overall.
_ORDER = {"ok": 0, "warn": 1, "fail": 2}

# (row key suffix, pip extra name, [modules that must import]).
_OPTIONAL_EXTRAS = [
    ("playwright", "playwright", ["playwright"]),
    ("geoip2", "geoip", ["geoip2"]),
    ("automation", "automation", ["pytweening", "loguru"]),
    ("markdown", "markdown", ["trafilatura", "markdownify"]),
    ("captcha", "captcha", ["aiohttp"]),
    ("vision", "vision", ["aiohttp"]),
    ("mcp", "mcp", ["mcp"]),
    ("agents", "agents", ["playwright"]),
]


@dataclass
class CheckResult:
    key: str
    label: str
    status: str          # "ok" | "warn" | "fail" | "skipped"
    detail: str = ""
    data: Optional[dict] = None
    hint: Optional[str] = None


@dataclass
class DoctorReport:
    checks: List[CheckResult]
    quick: bool
    header: dict

    @property
    def overall(self) -> str:
        worst = "ok"
        for c in self.checks:
            if c.status == "skipped":
                continue
            if _ORDER.get(c.status, 0) > _ORDER.get(worst, 0):
                worst = c.status
        return worst

    @property
    def counts(self) -> dict:
        out = {"ok": 0, "warn": 0, "fail": 0, "skipped": 0}
        for c in self.checks:
            out[c.status] = out.get(c.status, 0) + 1
        return out


# --- small helpers --------------------------------------------------------

def _dist_version() -> Optional[str]:
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version("huligan")
        except PackageNotFoundError:
            return None
    except Exception:
        return None


def _attr_version() -> Optional[str]:
    try:
        import huligan
        return getattr(huligan, "__version__", None)
    except Exception:
        return None


def _dep_ok(mods) -> bool:
    for m in mods:
        try:
            if importlib.util.find_spec(m) is None:
                return False
        except Exception:
            return False
    return True


def _host_platform() -> str:
    if sys.platform.startswith("win"):
        return "Win32"
    if sys.platform == "darwin":
        return "MacIntel"
    return "Linux x86_64"


def _binary_classify(path: Path):
    """Return ``(source, is_huligan)`` for a resolved Chrome path.

    ``is_huligan`` is True only for the auto-installer cache, ``$HULIGAN_CHROME``,
    a package-sibling release bundle, or a cwd ``chrome.exe`` - never for a
    system-PATH chrome (which could be the operator's real browser).
    """
    try:
        rp = path.resolve()
    except Exception:
        rp = path
    env = os.environ.get("HULIGAN_CHROME")
    if env:
        try:
            if rp == Path(env).resolve():
                return "env", True
        except Exception:
            pass
    try:
        cache_root = installer._cache_root().resolve()
        if cache_root == rp or cache_root in rp.parents:
            return "cache", True
    except Exception:
        pass
    try:
        pkg_parent = Path(installer.__file__).resolve().parent.parent
        if pkg_parent in rp.parents:
            return "package", True
    except Exception:
        pass
    try:
        if rp.parent == Path.cwd().resolve() and rp.name.lower() == "chrome.exe":
            return "cwd", True
    except Exception:
        pass
    return "path", False


def _probe_cdp_version(cdp_url: str) -> Optional[str]:
    try:
        with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=5) as r:
            return json.load(r).get("Browser")
    except Exception:
        return None


# --- individual checks ----------------------------------------------------

def _check_sdk_version() -> CheckResult:
    dist, attr = _dist_version(), _attr_version()
    data = {"dist": dist, "attr": attr, "build": BUILD_NUMBER}
    if dist is None:
        return CheckResult("sdk_version", "SDK version", "warn",
                           f"running from source (__version__ {attr}); not an installed distribution",
                           data, "pip install -e .  to register the distribution metadata")
    if attr is not None and dist != attr:
        return CheckResult("sdk_version", "SDK version", "warn",
                           f"distribution {dist} != huligan.__version__ {attr}", data,
                           "align huligan/__init__.py __version__ with pyproject version")
    return CheckResult("sdk_version", "SDK version", "ok", f"{dist} (Build {BUILD_NUMBER})", data)


def _check_chrome_target() -> CheckResult:
    try:
        channel, source = installer.effective_channel()
    except Exception as e:
        return CheckResult("chrome_target", "Chrome target", "warn", f"channel unresolved: {e}")
    return CheckResult(
        "chrome_target", "Chrome target", "ok",
        f"Chrome {CHROME_VERSION}, channel {channel} (from {source}), .conf schema v{CONF_SCHEMA_VERSION}",
        {"chrome_version": CHROME_VERSION, "channel": channel,
         "source": source, "conf_schema": CONF_SCHEMA_VERSION})


def _check_binary() -> CheckResult:
    from .chrome import find_chrome
    try:
        path = find_chrome(auto_install=False)
    except FileNotFoundError:
        return CheckResult("binary", "Chrome binary", "fail",
                           "patched Chrome not found (cache / $HULIGAN_CHROME / cwd)",
                           None, "huligan chrome update   # downloads the pinned build")
    except Exception as e:
        return CheckResult("binary", "Chrome binary", "fail", f"resolution error: {e}")
    src, is_hul = _binary_classify(path)
    data = {"path": str(path), "source": src}
    if is_hul:
        return CheckResult("binary", "Chrome binary", "ok", str(path), data)
    return CheckResult("binary", "Chrome binary", "warn",
                       f"{path} (system-PATH chrome - not the patched Huligan build)",
                       data, "huligan chrome update   # fetch the patched build")


def _check_launch(binary_result: CheckResult) -> CheckResult:
    # Never launch a system-PATH chrome (could be the operator's real browser).
    src = (binary_result.data or {}).get("source")
    if binary_result.status == "fail":
        return CheckResult("launch", "Launch smoke-test", "fail", "no binary to launch (see binary check)")
    if src not in ("env", "cache", "package", "cwd"):
        return CheckResult("launch", "Launch smoke-test", "warn",
                           "no patched Huligan binary to smoke-test (refusing to launch system Chrome)")
    binary_path = (binary_result.data or {}).get("path")
    tmp_conf = None
    udd = None
    res = None
    try:
        from .fingerprint import FingerprintProfile
        from .persistent import launch_persistent
        conf_text = FingerprintProfile.from_seed(0).to_conf()
        fd, name = tempfile.mkstemp(suffix=".conf", prefix="huligan_doctor_")
        os.close(fd)
        tmp_conf = Path(name)
        tmp_conf.write_text(conf_text if isinstance(conf_text, str) else str(conf_text), encoding="utf-8")
        udd = Path(tempfile.mkdtemp(prefix="huligan_doctor_udd_"))
        res = launch_persistent(profile_path=tmp_conf, chrome_path=binary_path,
                                user_data_dir=udd, headless=True, geoip=False,
                                wait_for_cdp=True, cdp_timeout=20.0)
        ver = _probe_cdp_version(res.cdp_url)
        if ver and CHROME_VERSION in ver:
            return CheckResult("launch", "Launch smoke-test", "ok",
                               f"CDP /json/version = {ver}", {"browser": ver})
        if ver:
            return CheckResult("launch", "Launch smoke-test", "warn",
                               f"launched, but reported {ver} != {CHROME_VERSION}", {"browser": ver})
        return CheckResult("launch", "Launch smoke-test", "ok", "CDP reachable (version unread)")
    except Exception as e:
        return CheckResult("launch", "Launch smoke-test", "fail", f"launch failed: {e}")
    finally:
        if res is not None:
            try:
                res.stop()
            except Exception:
                pass
        if tmp_conf is not None:
            try:
                tmp_conf.unlink()
            except OSError:
                pass
        if udd is not None:
            shutil.rmtree(udd, ignore_errors=True)


def _check_geoip_module() -> CheckResult:
    try:
        from . import geoip
        if getattr(geoip, "HAS_GEOIP2", False):
            return CheckResult("geoip_module", "GeoIP module", "ok", "geoip2 importable")
        return CheckResult("geoip_module", "GeoIP module", "warn",
                           "geoip2 not installed - online ip-api fallback still works",
                           None, "pip install huligan[geoip]")
    except Exception as e:
        return CheckResult("geoip_module", "GeoIP module", "warn", f"probe error: {e}")


def _check_geoip_db() -> CheckResult:
    try:
        from . import geoip
        found = [str(p) for p in getattr(geoip, "GEOIP_DB_PATHS", []) if Path(p).is_file()]
        if found:
            return CheckResult("geoip_db", "GeoIP local DB", "ok", found[0], {"paths": found})
        return CheckResult("geoip_db", "GeoIP local DB", "warn",
                           "no local GeoLite2-City.mmdb - using online fallback",
                           None, "download GeoLite2-City.mmdb (see docs/GEOIP_SETUP.md)")
    except Exception as e:
        return CheckResult("geoip_db", "GeoIP local DB", "warn", f"probe error: {e}")


def _check_fonts() -> CheckResult:
    host = _host_platform()
    try:
        from .data.font_lists import get_random_fonts
        fonts = get_random_fonts(host)
        if fonts:
            return CheckResult("fonts", "Fonts data", "ok", f"{host}: {len(fonts)} families",
                               {"platform": host, "count": len(fonts)})
        return CheckResult("fonts", "Fonts data", "fail", "empty font list (corrupt install)")
    except Exception as e:
        return CheckResult("fonts", "Fonts data", "fail", f"font data error: {e}")


def _check_platform() -> CheckResult:
    if sys.platform.startswith("win"):
        return CheckResult("platform", "Host platform", "ok", "win32 (patched binary supported)")
    return CheckResult("platform", "Host platform", "warn",
                       f"{sys.platform}: SDK/fingerprint work, but the patched binary is win64-only",
                       {"platform": sys.platform})


def _check_manifest() -> CheckResult:
    try:
        m = installer._safe_fetch_manifest()
        if m:
            return CheckResult("manifest", "Release manifest", "ok",
                               f"reachable - latest {m.get('latest', '?')}", {"latest": m.get("latest")})
        return CheckResult("manifest", "Release manifest", "warn",
                           "unreachable (offline) - the pinned build still launches")
    except Exception as e:
        return CheckResult("manifest", "Release manifest", "warn", f"fetch error: {e}")


def _check_deps() -> List[CheckResult]:
    out: List[CheckResult] = []
    for key, extra, mods in _OPTIONAL_EXTRAS:
        if _dep_ok(mods):
            out.append(CheckResult(f"deps.{key}", f"extra: {key}", "ok", "installed", {"modules": mods}))
        else:
            out.append(CheckResult(f"deps.{key}", f"extra: {key}", "warn", "missing",
                                   {"modules": mods}, f"pip install huligan[{extra}]"))
    tq = _dep_ok(["tqdm"])
    out.append(CheckResult("deps.tqdm", "dep: tqdm", "ok" if tq else "warn",
                           "installed" if tq else "missing (declared as a hard dependency)",
                           None, None if tq else "pip install tqdm"))
    return out


# --- orchestration + rendering -------------------------------------------

def collect_info() -> dict:
    try:
        channel, source = installer.effective_channel()
    except Exception:
        channel, source = ("?", "?")
    try:
        cache_dir = str(installer._cache_root())
    except Exception:
        cache_dir = ""
    try:
        builds = installer.installed_versions()
    except Exception:
        builds = []
    return {
        "sdk_version": _dist_version(),
        "sdk_version_attr": _attr_version(),
        "build_number": BUILD_NUMBER,
        "chrome_version": CHROME_VERSION,
        "channel": channel,
        "channel_source": source,
        "conf_schema": CONF_SCHEMA_VERSION,
        "platform": sys.platform,
        "cache_dir": cache_dir,
        "installed_builds": list(builds),
        "extras": {key: _dep_ok(mods) for key, _extra, mods in _OPTIONAL_EXTRAS},
    }


def run_checks(quick: bool = False) -> DoctorReport:
    checks: List[CheckResult] = [_check_sdk_version(), _check_chrome_target()]
    binr = _check_binary()
    checks.append(binr)
    if quick:
        checks.append(CheckResult("launch", "Launch smoke-test", "skipped", "skipped (--quick)"))
    else:
        checks.append(_check_launch(binr))
    checks.append(_check_geoip_module())
    checks.append(_check_geoip_db())
    checks.append(_check_fonts())
    checks.append(_check_platform())
    if quick:
        checks.append(CheckResult("manifest", "Release manifest", "skipped", "skipped (--quick)"))
    else:
        checks.append(_check_manifest())
    checks.extend(_check_deps())
    return DoctorReport(checks=checks, quick=quick, header=collect_info())


_MARK = {"ok": "OK", "warn": "WARN", "fail": "FAIL", "skipped": "SKIP"}
_COLOR = {"ok": "32", "warn": "33", "fail": "31", "skipped": "90"}


def _use_color() -> bool:
    try:
        return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    except Exception:
        return False


def _marker(status: str) -> str:
    plain = f"[{_MARK.get(status, status.upper())}]".ljust(6)
    if _use_color():
        return f"\033[{_COLOR.get(status, '0')}m{plain}\033[0m"
    return plain


def render_text(report: DoctorReport) -> str:
    h = report.header
    lines = [
        f"huligan doctor - Build {h.get('build_number')} (Chrome {h.get('chrome_version')}), "
        f"channel: {h.get('channel')} (from {h.get('channel_source')}), .conf schema v{h.get('conf_schema')}",
        "",
    ]
    for c in report.checks:
        lines.append(f"  {_marker(c.status)} {c.label:<20} {c.detail}")
        if c.hint and c.status in ("warn", "fail"):
            lines.append(f"         hint: {c.hint}")
    cn = report.counts
    tail = f"  {cn['ok']} OK, {cn['warn']} WARN, {cn['fail']} FAIL"
    if cn["skipped"]:
        tail += f", {cn['skipped']} SKIP"
    tail += f" - overall: {report.overall.upper()}"
    lines += ["", tail]
    return "\n".join(lines)


def render_json(report: DoctorReport) -> str:
    return json.dumps({
        "huligan": report.header,
        "overall": report.overall,
        "summary": report.counts,
        "quick": report.quick,
        "checks": [
            {"key": c.key, "label": c.label, "status": c.status,
             "detail": c.detail, "data": c.data, "hint": c.hint}
            for c in report.checks
        ],
    }, indent=2)


def render_info_text(info: dict) -> str:
    lines = [
        f"SDK:           {info.get('sdk_version')} (Build {info.get('build_number')})",
        f"Chrome:        {info.get('chrome_version')}",
        f"Channel:       {info.get('channel')} (from {info.get('channel_source')})",
        f".conf schema:  v{info.get('conf_schema')}",
        f"Platform:      {info.get('platform')}",
        f"Cache dir:     {info.get('cache_dir')}",
    ]
    builds = info.get("installed_builds") or []
    lines.append(f"Cached builds: {', '.join(builds) if builds else '(none)'}")
    extras = info.get("extras") or {}
    present = [k for k, v in extras.items() if v]
    missing = [k for k, v in extras.items() if not v]
    lines.append(f"Extras present: {', '.join(present) or '(none)'}")
    lines.append(f"Extras missing: {', '.join(missing) or '(none)'}")
    return "\n".join(lines)
