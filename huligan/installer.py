"""Huligan Chrome binary auto-installer.

The patched Chrome binary lives in a separate public mirror
(github.com/S1d18/huligan-releases). On first ``Browser()`` call the
SDK downloads and caches it locally; subsequent runs hit the cache.

Cache layout:
    ~/.huligan/chrome/{version}/chrome.exe   extracted browser
    ~/.huligan/chrome/{version}.ok           sentinel marking a successful install
                                             (JSON with the verified sha256; older
                                             SDKs wrote the bare version string)
    ~/.huligan/chrome/{version}.lock         inter-process install lock
    ~/.huligan/chrome/{version}.tmp-{pid}    staging dir while extracting

Environment overrides:
    HULIGAN_CHROME=path           explicit binary, skips download
    HULIGAN_CHROME_DIR=dir        custom cache directory
    HULIGAN_RELEASES_REPO=user/r  custom GitHub repo (default: S1d18/huligan-releases)
    HULIGAN_GH_TOKEN=token        Authorization header (needed while the repo is private)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional, Tuple

from .conf_spec import CONF_SCHEMA_VERSION
from .version import CHROME_VERSION

log = logging.getLogger("huligan.installer")


class IncompatibleBuildError(RuntimeError):
    """A resolved Chrome build needs a newer .conf schema than this SDK emits.

    Raised by version resolution when the manifest's ``min_conf_schema`` for the
    target build exceeds :data:`huligan.conf_spec.CONF_SCHEMA_VERSION`. Distinct
    from a plain RuntimeError so callers (e.g. ``find_chrome``) can degrade to the
    pinned build instead of failing hard.
    """


DEFAULT_REPO = "S1d18/huligan-releases"
ASSET_NAME_TEMPLATE = "huligan-chrome-{version}-win64.zip"
GH_API = "https://api.github.com"
# Public manifest listing the latest published build + per-version metadata.
MANIFEST_URL_TEMPLATE = "https://raw.githubusercontent.com/{repo}/main/manifest.json"

# Progress callback signature: (downloaded_bytes, total_bytes); total may be 0
# if the server omits Content-Length.
ProgressCallback = Callable[[int, int], None]

# Which channel drives version resolution when no explicit version is given.
#   pinned  -> version.CHROME_VERSION, sha from _KNOWN_SHA256; never touches the
#              network (reproducible for farms / the Chrome checker).
#   stable  -> manifest["channels"]["stable"] if present, else manifest["latest"].
#   latest  -> manifest["channels"]["latest"] if present, else manifest["latest"].
DEFAULT_CHANNEL = "pinned"

# How long a locally cached manifest.json is trusted before we re-fetch. The
# manifest only changes when the operator publishes a build, so a day is ample
# and keeps Browser() off the network on the hot path.
_MANIFEST_TTL_SECONDS = 24 * 3600
# When the network is down an expired cache is still served (offline degrade),
# but not forever: past this age the stale copy is refused so a machine that
# has been offline for weeks does not keep resolving channels from an ancient
# manifest (and its sha256 / min_conf_schema) without anyone noticing.
_MANIFEST_STALE_MAX_SECONDS = 14 * 24 * 3600
_PLATFORM_KEY = "win64"

# SHA256 of officially published archives. Verified before extraction.
_KNOWN_SHA256 = {
    "147.0.7727.56": "a0b84882d1c3d8686bc5083be5ea43c43b0d6d85db63ae335b11b6bbdb4d0e28",
    "148.0.7778.97": "52386c1fa6d44b20b594db4ee50d7914fecedbe4d8ec3a738739b13cebceb219",
    "149.0.7827.54": "b251dcf3137c11e4cfc5c1969022e5fc67ac79b38383db91fc89556d7f373e2f",
    "150.0.7871.101": "241da6d702b6adc0be1baaaa885e910e4e419e4e07530b270505ff4946c72617",
    "151.0.7922.76": "46dce52701ad47d0e8b25ed44faa12cef7bcc093f04f39ff2cceefa278a2594b",
    "152.0.7977.65": "1176597f64cedb783f3680d77e3c71aa63f95eb3bbfbea4a91c36d1c8bc34299",
}


# A Chrome build version is exactly four dot-separated decimal numbers. It is
# used as a directory / file name under the cache root, so anything else ("",
# "..", "../x", an absolute path) must be rejected before it reaches the
# filesystem (VER-PATH-01: remove_version('..') used to delete the cache root's
# parent).
_VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+")


def validate_version(version) -> str:
    """Return ``version`` if it is a dotted four-part numeric build version.

    Raises ``ValueError`` otherwise. Call before using a version in any path.
    """
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise ValueError(
            f"Invalid Chrome version {version!r}: expected four dot-separated "
            f"numbers, e.g. {CHROME_VERSION}"
        )
    return version


def _version_paths(version: str) -> Tuple[Path, Path, Path]:
    """Validated ``(root, version_dir, sentinel)`` for ``version``.

    Belt and braces on top of :func:`validate_version`: the resolved paths must
    stay strictly inside the cache root.
    """
    validate_version(version)
    root = _cache_root()
    target_dir = root / version
    sentinel = root / f"{version}.ok"
    root_resolved = root.resolve()
    for path in (target_dir, sentinel):
        resolved = path.resolve()
        if resolved == root_resolved or not resolved.is_relative_to(root_resolved):
            raise ValueError(f"Chrome version {version!r} escapes the cache root {root}")
    return root, target_dir, sentinel


def _cache_root() -> Path:
    override = os.environ.get("HULIGAN_CHROME_DIR")
    if override:
        return Path(override)
    return Path.home() / ".huligan" / "chrome"


def _releases_repo() -> str:
    return os.environ.get("HULIGAN_RELEASES_REPO", DEFAULT_REPO)


def _manifest_cache_path(repo: Optional[str] = None) -> Path:
    """Where the release manifest of ``repo`` is cached (under the cache root).

    Keyed by repo: switching ``HULIGAN_RELEASES_REPO`` must not serve another
    repo's manifest. The default repo keeps the historical ``manifest.json``.
    """
    repo = repo if repo is not None else _releases_repo()
    if repo == DEFAULT_REPO:
        return _cache_root() / "manifest.json"
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", repo).strip("._")[:60] or "repo"
    digest = hashlib.sha256(repo.encode("utf-8")).hexdigest()[:10]
    return _cache_root() / f"manifest-{slug}-{digest}.json"


def _config_path() -> Path:
    """Persisted CLI config (channel / exact pin) under the cache root."""
    return _cache_root() / "config.json"


def _load_config() -> dict:
    """Load the persisted config, or {} if absent/unreadable."""
    try:
        return json.loads(_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(cfg: dict) -> None:
    """Persist the config atomically (temp file + ``os.replace``): a crash or a
    concurrent reader never sees a half-written ``config.json``."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        _unlink_quiet(tmp)


# A channel name is a manifest key ("pinned", "stable", "latest", ...).
_CHANNEL_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}")


def get_launch_selection() -> dict:
    """The persisted launch selection: ``{"channel": str|None, "pinned_version": str|None}``.

    Only the persisted config (what :func:`set_launch_selection` / ``huligan
    chrome pin`` wrote); ``HULIGAN_CHROME_CHANNEL`` is not applied here — use
    :func:`effective_channel` / :func:`resolve_launch_target` for what is in force.
    """
    cfg = _load_config()
    channel = cfg.get("channel")
    pinned = cfg.get("pinned_version")
    return {
        "channel": str(channel) if channel else None,
        "pinned_version": str(pinned) if pinned else None,
    }


def set_launch_selection(version: Optional[str] = None,
                         channel: Optional[str] = None) -> dict:
    """Persist which Chrome build launches use; the public setter behind
    ``huligan chrome pin`` / ``update --channel`` (apps should call this
    instead of the private config helpers).

    * ``version`` given   -> exact pin: ``channel="pinned"`` + ``pinned_version``.
      ``version`` must be a four-part numeric build (``ValueError`` otherwise);
      combining it with a channel other than ``"pinned"`` is a ``ValueError``.
    * only ``channel``    -> follow that channel; any exact pin is cleared.
    * neither             -> clear both: back to the SDK's built-in default.

    Nothing is downloaded or resolved here. Other config keys are preserved and
    the write is atomic. Returns the new selection (as :func:`get_launch_selection`).
    """
    if channel is not None:
        if not isinstance(channel, str) or not _CHANNEL_RE.fullmatch(channel.strip().lower()):
            raise ValueError(f"Invalid channel {channel!r}")
        channel = channel.strip().lower()
    if version is not None:
        validate_version(version)
        if channel not in (None, "pinned"):
            raise ValueError(
                f"An exact version pin implies channel 'pinned', got {channel!r}")
    cfg = _load_config()
    if not isinstance(cfg, dict):
        cfg = {}
    if version is not None:
        cfg["channel"] = "pinned"
        cfg["pinned_version"] = version
    elif channel is not None:
        cfg["channel"] = channel
        cfg.pop("pinned_version", None)
    else:
        cfg.pop("channel", None)
        cfg.pop("pinned_version", None)
    _save_config(cfg)
    return get_launch_selection()


def effective_channel() -> Tuple[str, str]:
    """The channel in force and where it came from: (channel, "env"|"config"|"default").

    ``HULIGAN_CHROME_CHANNEL`` (env) overrides the persisted config, which
    overrides the built-in ``pinned`` default.
    """
    env = os.environ.get("HULIGAN_CHROME_CHANNEL")
    if env:
        return env.strip().lower(), "env"
    cfg = _load_config()
    if cfg.get("channel"):
        return str(cfg["channel"]).strip().lower(), "config"
    return DEFAULT_CHANNEL, "default"


def resolve_launch_target() -> Tuple[str, Optional[str]]:
    """Resolve (version, sha256) for launch, honouring env then persisted config.

    Env override wins whole; only a config ``pinned_version`` pins an exact build
    (env never carries one). This is the single entry point ``find_chrome`` uses.
    """
    channel, source = effective_channel()
    if channel == "pinned":
        if source != "env":
            pinned_version = _load_config().get("pinned_version")
            if pinned_version:
                return _resolve_target(str(pinned_version), None)
        return _resolve_target(None, "pinned")
    return _resolve_target(None, channel)


def _version_key(version: str):
    """Sort key for dotted numeric versions (e.g. 150.0.7871.101)."""
    parts = []
    for chunk in str(version).split("."):
        parts.append(int(chunk) if chunk.isdigit() else 0)
    return tuple(parts)


def installed_versions() -> list:
    """Cached Chrome versions that are fully extracted and marked OK, newest first."""
    root = _cache_root()
    if not root.is_dir():
        return []
    found = []
    for entry in root.iterdir():
        if (_VERSION_RE.fullmatch(entry.name)
                and entry.is_dir()
                and (entry / "chrome.exe").is_file()
                and (root / f"{entry.name}.ok").exists()):
            found.append(entry.name)
    return sorted(found, key=_version_key, reverse=True)


def remove_version(version: str) -> bool:
    """Delete a cached Chrome version (dir + sentinel). Returns True if anything went.

    Raises ``ValueError`` for anything that is not a four-part numeric version.
    """
    _root, target, sentinel = _version_paths(version)
    removed = False
    # Sentinel first: an interrupted removal must not look like an install.
    if sentinel.exists():
        sentinel.unlink()
        removed = True
    if target.exists():
        shutil.rmtree(target)
        removed = True
    return removed


def _fetch_manifest(force: bool = False, timeout: float = 10.0) -> dict:
    """Return the release ``manifest.json``, TTL-cached under the cache root.

    A fresh cache (younger than ``_MANIFEST_TTL_SECONDS``) short-circuits with
    no network. On a cache miss/expiry we fetch from the releases repo; if that
    fails but a (stale) cache exists we return the stale copy so a network blip
    never bricks resolution — logged with its age, and only up to
    ``_MANIFEST_STALE_MAX_SECONDS``. Raises when there is neither network nor a
    usable cache to fall back on. The cache is per ``HULIGAN_RELEASES_REPO``.
    """
    repo = _releases_repo()
    cache = _manifest_cache_path(repo)
    cached_data = None
    age = None
    if cache.is_file():
        try:
            cached_data = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            cached_data = None
        try:
            age = time.time() - cache.stat().st_mtime
        except OSError:
            age = None  # unstattable: treat as expired, and too old to trust offline

    if not force and cached_data is not None and age is not None:
        if age < _MANIFEST_TTL_SECONDS:
            return cached_data

    token = os.environ.get("HULIGAN_GH_TOKEN")
    url = MANIFEST_URL_TEMPLATE.format(repo=repo)
    try:
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        if cached_data is not None and age is not None and age <= _MANIFEST_STALE_MAX_SECONDS:
            # Stale, but better than nothing (offline degrade).
            log.warning(
                "Release manifest for %s unreachable (%s); using cached copy %.1f h old",
                repo, exc, age / 3600,
            )
            return cached_data
        if cached_data is not None:
            log.warning(
                "Release manifest for %s unreachable (%s); cached copy is too old "
                "to trust (%s)", repo, exc,
                "age unknown" if age is None else f"{age / 86400:.1f} days",
            )
        raise

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass  # cache write is best-effort; resolution still works from `data`
    return data


def _channel_version(manifest: dict, channel: str) -> str:
    """Resolve a channel name to a concrete version string from the manifest."""
    channels = manifest.get("channels") or {}
    if channel in channels and channels[channel]:
        return str(channels[channel])
    latest = manifest.get("latest")
    if latest:
        return str(latest)
    raise RuntimeError(
        f"Manifest has no channel {channel!r} and no 'latest' key "
        f"(repo {os.environ.get('HULIGAN_RELEASES_REPO', DEFAULT_REPO)})."
    )


def _sha_from_manifest(version: str, manifest: Optional[dict] = None) -> Optional[str]:
    """Dig the win64 sha256 for ``version`` out of the manifest, or None."""
    try:
        manifest = manifest if manifest is not None else _fetch_manifest()
        return str(manifest["versions"][version][_PLATFORM_KEY]["sha256"])
    except Exception:
        return None


def _safe_fetch_manifest() -> Optional[dict]:
    """Best-effort manifest fetch that returns None instead of raising."""
    try:
        return _fetch_manifest()
    except Exception:
        return None


def _min_conf_schema(version: str, manifest: dict) -> Optional[int]:
    """The .conf schema version a build requires, or None if unspecified."""
    try:
        raw = manifest["versions"][version].get("min_conf_schema")
        return int(raw) if raw is not None else None
    except Exception:
        return None


def _check_conf_compat(version: str, manifest: dict) -> None:
    """Raise IncompatibleBuildError if this SDK is too old for ``version``.

    No-op when the manifest omits ``min_conf_schema`` for the build (older
    manifests) or when the SDK's schema is new enough.
    """
    required = _min_conf_schema(version, manifest)
    if required is not None and required > CONF_SCHEMA_VERSION:
        raise IncompatibleBuildError(
            f"Chrome build {version} requires .conf schema v{required}, but this "
            f"huligan-sdk emits v{CONF_SCHEMA_VERSION}. Launching it would produce "
            f"an incomplete fingerprint. Upgrade the SDK:\n"
            f"  pip install --upgrade huligan"
        )


def _resolve_target(
    version: Optional[str],
    channel: Optional[str],
) -> Tuple[str, Optional[str]]:
    """Resolve (version, expected_sha256) from an explicit version or a channel.

    Precedence keeps the ``pinned`` path fully offline: a version baked into
    ``_KNOWN_SHA256`` (including CHROME_VERSION) never triggers a manifest fetch
    and is compatible by construction — it shipped with this SDK. Only unknown
    explicit versions or non-pinned channels consult the manifest, and those are
    gated on ``min_conf_schema`` before we agree to download them.
    """
    if version is not None:
        validate_version(version)
        if version in _KNOWN_SHA256:
            # Baked-in build: offline, and known-compatible with this SDK.
            return version, _KNOWN_SHA256[version]
        # Unknown explicit version: consult the manifest for sha + compat gate.
        manifest = _safe_fetch_manifest()
        if manifest is not None:
            _check_conf_compat(version, manifest)
        sha = _sha_from_manifest(version, manifest) if manifest is not None else None
        return version, sha

    channel = (channel or DEFAULT_CHANNEL).strip().lower()
    if channel == "pinned":
        sha = _KNOWN_SHA256.get(CHROME_VERSION) or _sha_from_manifest(CHROME_VERSION)
        return CHROME_VERSION, sha

    manifest = _fetch_manifest()
    resolved = validate_version(_channel_version(manifest, channel))
    _check_conf_compat(resolved, manifest)
    sha = _sha_from_manifest(resolved, manifest)
    return resolved, sha


def resolve_version(channel: str = DEFAULT_CHANNEL) -> Tuple[str, Optional[str]]:
    """Public: resolve (version, expected_sha256) for a channel.

    ``pinned`` (default) returns CHROME_VERSION with no network. ``stable`` /
    ``latest`` consult the TTL-cached release manifest.
    """
    return _resolve_target(None, channel)


def _resolve_asset(repo: str, version: str, asset_name: str, token: str) -> Tuple[str, dict]:
    """Look up the release asset id via GitHub API and return its download URL.

    GitHub's browser-facing ``releases/download/...`` URL returns 404 for
    private repos even with a Bearer token. The API endpoint
    ``/repos/{owner}/{repo}/releases/assets/{id}`` works for both private
    and public repos and is the only path GitHub officially supports for
    authenticated downloads.
    """
    api_url = f"{GH_API}/repos/{repo}/releases/tags/v{version}"
    req = urllib.request.Request(api_url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req) as response:
        release = json.loads(response.read())

    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            return f"{GH_API}/repos/{repo}/releases/assets/{asset['id']}", release

    available = [a.get("name") for a in release.get("assets", [])]
    raise RuntimeError(
        f"Asset {asset_name!r} not found in release v{version} of {repo}.\n"
        f"Available assets: {available}"
    )


def _build_browser_url(version: str) -> str:
    repo = os.environ.get("HULIGAN_RELEASES_REPO", DEFAULT_REPO)
    asset = ASSET_NAME_TEMPLATE.format(version=version)
    return f"https://github.com/{repo}/releases/download/v{version}/{asset}"


def _download(
    url: str,
    dest: Path,
    token: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    """Stream ``url`` to ``dest``.

    With ``progress_callback`` set, report progress through it (GUI use — no
    console). Otherwise fall back to a ``tqdm`` bar if tqdm is importable, else
    download silently. tqdm is therefore an optional dependency, not required.
    """
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        # Critical for the API asset endpoint — without it GitHub returns
        # JSON metadata instead of the binary.
        req.add_header("Accept", "application/octet-stream")

    bar = None
    if progress_callback is None:
        try:
            from tqdm import tqdm
            bar = None  # created once total is known
        except Exception:
            tqdm = None  # noqa: F841 — silent download

    with urllib.request.urlopen(req) as response:
        total = int(response.headers.get("Content-Length", 0))
        dest.parent.mkdir(parents=True, exist_ok=True)
        chunk = 1024 * 64
        downloaded = 0
        if progress_callback is None:
            try:
                from tqdm import tqdm
                bar = tqdm(total=total, unit="B", unit_scale=True,
                           unit_divisor=1024, desc=dest.name)
            except Exception:
                bar = None
        try:
            with open(dest, "wb") as fh:
                while True:
                    buf = response.read(chunk)
                    if not buf:
                        break
                    fh.write(buf)
                    downloaded += len(buf)
                    if progress_callback is not None:
                        progress_callback(downloaded, total)
                    elif bar is not None:
                        bar.update(len(buf))
        finally:
            if bar is not None:
                bar.close()


def _verify_sha256(path: Path, expected: str) -> None:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for buf in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(buf)
    actual = h.hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"SHA256 mismatch for {path.name}\n"
            f"  expected: {expected}\n"
            f"  actual:   {actual}"
        )


def _flatten_top_level(target_dir: Path) -> None:
    """If extraction produced a single top-level folder, lift its contents up."""
    entries = list(target_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for child in inner.iterdir():
            shutil.move(str(child), str(target_dir / child.name))
        inner.rmdir()


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _write_sentinel(sentinel: Path, version: str, sha256: str) -> None:
    """Atomically write the ``{version}.ok`` marker, recording the verified sha256.

    Format: JSON ``{"version": ..., "sha256": ...}``. Older SDKs wrote the bare
    version string; :func:`is_installed` only checks existence, so both count.
    """
    tmp = sentinel.with_name(f"{sentinel.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps({"version": version, "sha256": sha256}), encoding="utf-8")
    os.replace(tmp, sentinel)


def _installed_sha256(version: str) -> Optional[str]:
    """sha256 recorded in the ``.ok`` sentinel, or ``None`` (absent / legacy)."""
    try:
        _root, _dir, sentinel = _version_paths(version)
        data = json.loads(sentinel.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if isinstance(data, dict) and data.get("sha256"):
        return str(data["sha256"])
    return None


def _install_matches(version: str, expected_sha: Optional[str]) -> bool:
    """False only when BOTH shas are known and differ.

    The ``.ok`` sentinel records the sha256 the build was verified against. If
    the expected sha (baked-in, or from the release manifest) is different, the
    same version was republished (a rebuild) and the cached tree is not the
    build clients should run. Unknown on either side (legacy sentinel, manifest
    offline) counts as a match: the working cache keeps being used.
    """
    if not expected_sha:
        return True
    installed = _installed_sha256(version)
    if not installed:
        return True
    return installed.strip().lower() == expected_sha.strip().lower()


@contextmanager
def _install_lock(root: Path, version: str, timeout: float = 3600.0, poll: float = 0.5):
    """Exclusive inter-process lock on ``{root}/{version}.lock``.

    Uses an OS byte-range / flock lock on an open handle, so the OS releases it
    if the holder dies: a crashed installer never leaves a stale lock behind.
    The lock file itself is left in place (deleting it would race other
    waiters). Raises ``TimeoutError`` after ``timeout`` seconds.
    """
    validate_version(version)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / f"{version}.lock"
    fh = open(lock_path, "a+b")
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                _try_lock(fh)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Another process is installing Chrome {version} "
                        f"(lock {lock_path} held for more than {timeout:.0f}s)"
                    )
                time.sleep(poll)
        try:
            yield
        finally:
            _unlock(fh)
    finally:
        fh.close()


if sys.platform == "win32":
    import msvcrt

    def _try_lock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh) -> None:
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _try_lock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def ensure_chrome(
    version: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
    *,
    channel: Optional[str] = None,
) -> Path:
    """Ensure the patched Chrome binary is installed; return path to ``chrome.exe``.

    Version selection:
        * ``version`` given      -> that exact version (explicit pin).
        * ``channel`` given      -> resolved from the release manifest
          (``stable`` / ``latest``), or ``pinned`` for CHROME_VERSION.
        * neither given          -> ``pinned`` (CHROME_VERSION), fully offline.

    The expected sha256 comes from the manifest when the version is not baked
    into ``_KNOWN_SHA256`` — so a new monthly build no longer needs an SDK edit.
    Without a known sha256 (manifest offline, or the version absent from it) the
    install is refused with ``RuntimeError``; nothing is downloaded.

    Idempotent: a hot cache short-circuits in O(1). Pass ``progress_callback``
    (``(downloaded, total)``) to drive a GUI progress bar instead of the console.
    """
    if sys.platform != "win32":
        raise RuntimeError(
            f"Huligan currently ships Windows binaries only "
            f"(detected platform: {sys.platform})."
        )

    version, expected_sha = _resolve_target(version, channel)

    root, target_dir, sentinel = _version_paths(version)
    chrome_exe = target_dir / "chrome.exe"

    installed = chrome_exe.is_file() and sentinel.exists()
    if installed and _install_matches(version, expected_sha):
        return chrome_exe

    # SEC-03: never download + extract a build we cannot verify. A version that
    # is neither baked into _KNOWN_SHA256 nor listed with a sha256 in the
    # release manifest (or the manifest is unreachable) is refused outright.
    if not expected_sha:
        raise RuntimeError(
            f"Refusing to install Chrome {version}: no known sha256 for it. It is "
            f"not baked into this SDK and the release manifest "
            f"({os.environ.get('HULIGAN_RELEASES_REPO', DEFAULT_REPO)}) is "
            f"unreachable or does not list it. Retry when online, pick a "
            f"published version, or upgrade the SDK."
        )

    if installed:
        # Same version, different sha: the build was republished. Reinstall,
        # but a working cached build is never lost to a failed replacement
        # (offline, download error, files in use by a running Chrome).
        log.warning(
            "Chrome %s in cache was verified against sha256 %s, but the expected "
            "sha256 is now %s (build republished); reinstalling",
            version, _installed_sha256(version), expected_sha,
        )
        try:
            return _install_build(version, expected_sha, progress_callback)
        except Exception as exc:
            log.warning(
                "Reinstall of Chrome %s failed (%s); keeping the cached build", version, exc)
            return chrome_exe
    return _install_build(version, expected_sha, progress_callback)


def _install_build(
    version: str,
    expected_sha: str,
    progress_callback: Optional[ProgressCallback] = None,
) -> Path:
    """Download, verify and atomically install ``version`` (under the lock)."""
    root, target_dir, sentinel = _version_paths(version)
    chrome_exe = target_dir / "chrome.exe"

    # One installer per version at a time, across processes (a GUI and a CLI,
    # or several SDK processes on a farm). Whoever waited re-checks the cache:
    # the first holder has usually finished the job.
    with _install_lock(root, version):
        working = chrome_exe.is_file() and sentinel.exists()
        if working and _install_matches(version, expected_sha):
            return chrome_exe
        # Not installed (or damaged). A stale sentinel must not survive into a
        # repair that might be interrupted. A WORKING build being replaced by a
        # rebuild keeps its sentinel until the new tree is ready to swap in.
        if not working:
            _unlink_quiet(sentinel)
        # Leftovers of a crashed installer for this version (we hold the lock,
        # so nobody else is using them).
        for leftover in root.glob(f"{version}.tmp-*"):
            shutil.rmtree(leftover, ignore_errors=True)
        for leftover in root.glob(f"{version}.old-*"):
            shutil.rmtree(leftover, ignore_errors=True)

        repo = os.environ.get("HULIGAN_RELEASES_REPO", DEFAULT_REPO)
        asset_name = ASSET_NAME_TEMPLATE.format(version=version)
        token = os.environ.get("HULIGAN_GH_TOKEN")

        if token:
            try:
                url, _ = _resolve_asset(repo, version, asset_name, token)
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise RuntimeError(
                        f"GitHub rejected HULIGAN_GH_TOKEN (HTTP 401). "
                        f"Re-issue it via `gh auth token` and re-export."
                    ) from exc
                if exc.code == 403:
                    raise RuntimeError(
                        f"GitHub denied access to {repo} (HTTP 403). "
                        f"Check that the token has 'repo' scope and that the "
                        f"account can see this repository."
                    ) from exc
                if exc.code == 404:
                    raise RuntimeError(
                        f"Release v{version} not found in {repo} (HTTP 404). "
                        f"Verify the version number and HULIGAN_RELEASES_REPO."
                    ) from exc
                raise
        else:
            url = _build_browser_url(version)

        print(f"[huligan] Chrome {version} not in cache, downloading...")
        print(f"[huligan] Source: {url}")

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            zip_path = tmp / asset_name

            try:
                _download(url, zip_path, token=token, progress_callback=progress_callback)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403, 404) and not token:
                    raise RuntimeError(
                        f"Could not download {url} (HTTP {exc.code}).\n"
                        f"If the mirror is still private, set HULIGAN_GH_TOKEN "
                        f"to a GitHub token with 'repo' scope and retry."
                    ) from exc
                raise

            _verify_sha256(zip_path, expected_sha)

            # Extract into a private staging dir next to the target (same volume,
            # so the final os.replace is a rename). The live dir is only touched
            # once a complete, checked tree exists.
            staging = root / f"{version}.tmp-{os.getpid()}"
            try:
                if staging.exists():
                    shutil.rmtree(staging)
                staging.mkdir(parents=True)
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(staging)
                _flatten_top_level(staging)
                if not (staging / "chrome.exe").is_file():
                    raise RuntimeError(
                        f"chrome.exe not found after extraction of {asset_name}"
                    )

                # The sentinel goes BEFORE the old tree: an interruption from here
                # on must never leave "{version}.ok" next to a half-replaced dir.
                old_marker = sentinel.read_bytes() if working else None
                _unlink_quiet(sentinel)
                aside = None
                if target_dir.exists():
                    # Move the old tree aside in one rename instead of deleting
                    # it in place: a Chrome still running from it makes the
                    # rename fail cleanly, where rmtree would half-delete it.
                    aside = root / f"{version}.old-{os.getpid()}"
                    try:
                        os.replace(target_dir, aside)
                    except OSError:
                        aside = None
                        if old_marker is not None:
                            sentinel.write_bytes(old_marker)  # old build intact
                            raise
                        shutil.rmtree(target_dir)
                try:
                    os.replace(staging, target_dir)
                except OSError:
                    if aside is not None and not target_dir.exists():
                        os.replace(aside, target_dir)
                        if old_marker is not None:
                            sentinel.write_bytes(old_marker)
                    raise
                if aside is not None:
                    shutil.rmtree(aside, ignore_errors=True)
            finally:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)

            _write_sentinel(sentinel, version, expected_sha)

        print(f"[huligan] Chrome {version} installed at {target_dir}")
        return chrome_exe


def ensure_binary(
    version: Optional[str] = None,
    *,
    channel: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Path:
    """Return the path to the patched Huligan Chrome, downloading + caching if needed.

    Public integration primitive - a thin alias of :func:`ensure_chrome` with a
    name that reads correctly at a third-party call site::

        options.binary_location = huligan.ensure_binary()

    Always resolves the *patched* build (as does :func:`huligan.find_chrome`,
    which never falls back to a vanilla Chrome from ``PATH`` or the CWD) - so an
    integration whose contract is "the patched binary" gets exactly that.
    """
    return ensure_chrome(version, progress_callback, channel=channel)


def is_installed(version: str = CHROME_VERSION) -> bool:
    """True if ``version`` is already extracted and marked OK in the cache.

    An invalid version string (not four dot-separated numbers) is never
    installed: returns ``False`` without touching the filesystem.
    """
    try:
        _root, target_dir, sentinel = _version_paths(version)
    except ValueError:
        return False
    return (target_dir / "chrome.exe").is_file() and sentinel.exists()


def latest_version(
    repo: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 10.0,
) -> Optional[str]:
    """Return the ``latest`` build version from the public release manifest.

    Reads the TTL-cached ``manifest.json`` (repo + token come from the
    ``HULIGAN_RELEASES_REPO`` / ``HULIGAN_GH_TOKEN`` environment variables; the
    ``repo``/``token`` params are accepted for backward compatibility but the
    env-driven cache is authoritative). Returns ``None`` on any network/parse
    error so callers can degrade to a "couldn't check" message rather than crashing.
    """
    try:
        data = _fetch_manifest(timeout=timeout)
        latest = data.get("latest")
        return str(latest) if latest else None
    except Exception:
        return None
