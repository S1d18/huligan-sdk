"""Huligan Antidetect — Chrome executable finder."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional


def find_chrome(
    explicit_path: Optional[Path] = None,
    env_var: str = "HULIGAN_CHROME",
    auto_install: bool = True,
) -> Path:
    """Find the Huligan Chrome executable.

    Search order:
        1. ``explicit_path`` argument
        2. ``$HULIGAN_CHROME`` environment variable
        3. ``./chrome.exe`` in the current working directory
        4. Sibling of the ``huligan`` package (release-bundle layout)
        5. ``~/.huligan/chrome/{version}/chrome.exe`` (auto-installer cache)
        6. ``chrome``/``chrome.exe`` on the system PATH
        7. If ``auto_install`` is True, downloads from the public mirror

    Raises:
        FileNotFoundError: if Chrome cannot be found and ``auto_install`` is False.
    """
    if explicit_path is not None:
        p = Path(explicit_path)
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"Chrome not found at explicit path: {explicit_path}")

    env_path = os.environ.get(env_var)
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p.resolve()

    cwd_chrome = Path("chrome.exe")
    if cwd_chrome.is_file():
        return cwd_chrome.resolve()

    package_dir = Path(__file__).parent
    for candidate in (
        package_dir.parent / "chrome.exe",
        package_dir.parent / "chrome" / "chrome.exe",
    ):
        if candidate.is_file():
            return candidate.resolve()

    from .installer import ensure_chrome, resolve_version, IncompatibleBuildError, _cache_root
    from .version import CHROME_VERSION

    # HULIGAN_CHROME_CHANNEL picks which version this machine tracks. Default
    # "pinned" reproduces the old behaviour exactly (CHROME_VERSION, no network);
    # "stable"/"latest" resolve from the release manifest. If manifest resolution
    # fails (offline + uncached) we degrade to the pinned version so a network
    # blip never bricks launch.
    channel = os.environ.get("HULIGAN_CHROME_CHANNEL", "pinned").strip().lower()
    if channel == "pinned":
        target_version = CHROME_VERSION
    else:
        try:
            target_version, _ = resolve_version(channel)
        except IncompatibleBuildError as exc:
            # The channel points at a build newer than this SDK's .conf schema.
            # Falling back to the pinned build keeps launch working with a
            # guaranteed-compatible browser instead of a degraded fingerprint.
            print(
                f"[huligan] {exc}\n"
                f"[huligan] Using pinned Chrome {CHROME_VERSION} instead."
            )
            target_version = CHROME_VERSION
        except Exception:
            target_version = CHROME_VERSION

    cached = _cache_root() / target_version / "chrome.exe"
    if cached.is_file():
        return cached.resolve()

    chrome_in_path = shutil.which("chrome") or shutil.which("chrome.exe")
    if chrome_in_path:
        return Path(chrome_in_path).resolve()

    if auto_install:
        return ensure_chrome(target_version).resolve()

    raise FileNotFoundError(
        "Huligan Chrome not found. Either:\n"
        f"  - pass chrome_path= to Browser()\n"
        f"  - set {env_var} environment variable\n"
        f"  - place chrome.exe in the current directory\n"
        f"  - call huligan.installer.ensure_chrome() to download it"
    )
