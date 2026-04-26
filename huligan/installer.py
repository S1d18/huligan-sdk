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
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from .version import CHROME_VERSION

DEFAULT_REPO = "S1d18/huligan-releases"
ASSET_NAME_TEMPLATE = "huligan-chrome-{version}-win64.zip"

# SHA256 of officially published archives. Verified before extraction.
_KNOWN_SHA256 = {
    "147.0.7727.56": "a0b84882d1c3d8686bc5083be5ea43c43b0d6d85db63ae335b11b6bbdb4d0e28",
}


def _cache_root() -> Path:
    override = os.environ.get("HULIGAN_CHROME_DIR")
    if override:
        return Path(override)
    return Path.home() / ".huligan" / "chrome"


def _build_url(version: str) -> str:
    repo = os.environ.get("HULIGAN_RELEASES_REPO", DEFAULT_REPO)
    asset = ASSET_NAME_TEMPLATE.format(version=version)
    return f"https://github.com/{repo}/releases/download/v{version}/{asset}"


def _download(url: str, dest: Path, token: Optional[str] = None) -> None:
    from tqdm import tqdm

    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/octet-stream")

    with urllib.request.urlopen(req) as response:
        total = int(response.headers.get("Content-Length", 0))
        dest.parent.mkdir(parents=True, exist_ok=True)
        chunk = 1024 * 64
        with open(dest, "wb") as fh, tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=dest.name,
        ) as bar:
            while True:
                buf = response.read(chunk)
                if not buf:
                    break
                fh.write(buf)
                bar.update(len(buf))


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


def ensure_chrome(version: str = CHROME_VERSION) -> Path:
    """Ensure the patched Chrome binary is installed; return path to ``chrome.exe``.

    Idempotent: a hot cache short-circuits in O(1).
    """
    if sys.platform != "win32":
        raise RuntimeError(
            f"Huligan currently ships Windows binaries only "
            f"(detected platform: {sys.platform})."
        )

    root = _cache_root()
    target_dir = root / version
    chrome_exe = target_dir / "chrome.exe"
    sentinel = root / f"{version}.ok"

    if chrome_exe.is_file() and sentinel.exists():
        return chrome_exe

    url = _build_url(version)
    token = os.environ.get("HULIGAN_GH_TOKEN")

    print(f"[huligan] Chrome {version} not in cache, downloading...")
    print(f"[huligan] Source: {url}")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        zip_path = tmp / ASSET_NAME_TEMPLATE.format(version=version)

        try:
            _download(url, zip_path, token=token)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404) and not token:
                raise RuntimeError(
                    f"Could not download {url} (HTTP {exc.code}).\n"
                    f"If the mirror is still private, set HULIGAN_GH_TOKEN "
                    f"to a GitHub token with 'repo' scope and retry."
                ) from exc
            raise

        expected = _KNOWN_SHA256.get(version)
        if expected:
            _verify_sha256(zip_path, expected)

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
