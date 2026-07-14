"""Huligan Chrome binary auto-installer.

The patched Chrome binary lives in a separate public mirror
(github.com/S1d18/huligan-releases). On first ``Browser()`` call the
SDK downloads and caches it locally; subsequent runs hit the cache.

Cache layout:
    ~/.huligan/chrome/{version}/chrome.exe   extracted browser
    ~/.huligan/chrome/{version}.ok           sentinel marking a successful install

Environment overrides:
    HULIGAN_CHROME=path           explicit binary, skips download
    HULIGAN_CHROME_DIR=dir        custom cache directory
    HULIGAN_RELEASES_REPO=user/r  custom GitHub repo (default: S1d18/huligan-releases)
    HULIGAN_GH_TOKEN=token        Authorization header (needed while the repo is private)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional, Tuple

from .conf_spec import CONF_SCHEMA_VERSION
from .version import CHROME_VERSION


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
_PLATFORM_KEY = "win64"

# SHA256 of officially published archives. Verified before extraction.
_KNOWN_SHA256 = {
    "147.0.7727.56": "a0b84882d1c3d8686bc5083be5ea43c43b0d6d85db63ae335b11b6bbdb4d0e28",
    "148.0.7778.97": "52386c1fa6d44b20b594db4ee50d7914fecedbe4d8ec3a738739b13cebceb219",
    "149.0.7827.54": "b251dcf3137c11e4cfc5c1969022e5fc67ac79b38383db91fc89556d7f373e2f",
    "150.0.7871.101": "241da6d702b6adc0be1baaaa885e910e4e419e4e07530b270505ff4946c72617",
}


def _cache_root() -> Path:
    override = os.environ.get("HULIGAN_CHROME_DIR")
    if override:
        return Path(override)
    return Path.home() / ".huligan" / "chrome"


def _manifest_cache_path() -> Path:
    """Where the release manifest is cached locally (under the cache root)."""
    return _cache_root() / "manifest.json"


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
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


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
        if (entry.is_dir()
                and (entry / "chrome.exe").is_file()
                and (root / f"{entry.name}.ok").exists()):
            found.append(entry.name)
    return sorted(found, key=_version_key, reverse=True)


def remove_version(version: str) -> bool:
    """Delete a cached Chrome version (dir + sentinel). Returns True if anything went."""
    root = _cache_root()
    removed = False
    target = root / version
    if target.exists():
        shutil.rmtree(target)
        removed = True
    sentinel = root / f"{version}.ok"
    if sentinel.exists():
        sentinel.unlink()
        removed = True
    return removed


def _fetch_manifest(force: bool = False, timeout: float = 10.0) -> dict:
    """Return the release ``manifest.json``, TTL-cached under the cache root.

    A fresh cache (younger than ``_MANIFEST_TTL_SECONDS``) short-circuits with
    no network. On a cache miss/expiry we fetch from the releases repo; if that
    fails but a (stale) cache exists we return the stale copy so a network blip
    never bricks resolution. Raises only when there is neither network nor any
    cache to fall back on.
    """
    cache = _manifest_cache_path()
    cached_data = None
    if cache.is_file():
        try:
            cached_data = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            cached_data = None

    if not force and cached_data is not None:
        try:
            age = time.time() - cache.stat().st_mtime
        except OSError:
            age = _MANIFEST_TTL_SECONDS + 1  # treat unstattable as expired
        if age < _MANIFEST_TTL_SECONDS:
            return cached_data

    repo = os.environ.get("HULIGAN_RELEASES_REPO", DEFAULT_REPO)
    token = os.environ.get("HULIGAN_GH_TOKEN")
    url = MANIFEST_URL_TEMPLATE.format(repo=repo)
    try:
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        if cached_data is not None:
            return cached_data  # stale, but better than nothing (offline degrade)
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
    resolved = _channel_version(manifest, channel)
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

    Idempotent: a hot cache short-circuits in O(1). Pass ``progress_callback``
    (``(downloaded, total)``) to drive a GUI progress bar instead of the console.
    """
    if sys.platform != "win32":
        raise RuntimeError(
            f"Huligan currently ships Windows binaries only "
            f"(detected platform: {sys.platform})."
        )

    version, expected_sha = _resolve_target(version, channel)

    root = _cache_root()
    target_dir = root / version
    chrome_exe = target_dir / "chrome.exe"
    sentinel = root / f"{version}.ok"

    if chrome_exe.is_file() and sentinel.exists():
        return chrome_exe

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

        if expected_sha:
            _verify_sha256(zip_path, expected_sha)

        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target_dir)

        _flatten_top_level(target_dir)

        if not chrome_exe.is_file():
            raise RuntimeError(
                f"chrome.exe not found after extraction at {target_dir}"
            )

        sentinel.write_text(version)

    print(f"[huligan] Chrome {version} installed at {target_dir}")
    return chrome_exe


def is_installed(version: str = CHROME_VERSION) -> bool:
    """True if ``version`` is already extracted and marked OK in the cache."""
    root = _cache_root()
    return (root / version / "chrome.exe").is_file() and (root / f"{version}.ok").exists()


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
