"""Huligan Antidetect — Chrome executable finder."""

from __future__ import annotations

import os
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
        3. Sibling of the ``huligan`` package (release-bundle layout)
        4. ``~/.huligan/chrome/{version}/chrome.exe`` (auto-installer cache),
           only when its ``{version}.ok`` marker says extraction completed
        5. If ``auto_install`` is True, downloads from the public mirror

    Deliberately NOT searched: ``./chrome.exe`` in the CWD and ``chrome`` on
    ``PATH``. Both silently resolved to a stock, unpatched Chrome - the worst
    possible outcome for an antidetect launch (audit SYS-04). Pass
    ``explicit_path`` / ``$HULIGAN_CHROME`` to use a custom binary on purpose.

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

    package_dir = Path(__file__).parent
    for candidate in (
        package_dir.parent / "chrome.exe",
        package_dir.parent / "chrome" / "chrome.exe",
    ):
        if candidate.is_file():
            return candidate.resolve()

    from .installer import (
        ensure_chrome, resolve_launch_target, IncompatibleBuildError, _cache_root, is_installed,
    )
    from .version import CHROME_VERSION

    # The launch target is HULIGAN_CHROME_CHANNEL (env) or the persisted CLI
    # config, defaulting to "pinned" = CHROME_VERSION with no network. A newer
    # channel build that this SDK's .conf schema can't feed degrades to the
    # pinned build (compat gate); any other resolution failure (offline +
    # uncached) also degrades, so a network blip never bricks launch.
    try:
        target_version, _ = resolve_launch_target()
    except IncompatibleBuildError as exc:
        print(
            f"[huligan] {exc}\n"
            f"[huligan] Using pinned Chrome {CHROME_VERSION} instead."
        )
        target_version = CHROME_VERSION
    except Exception:
        target_version = CHROME_VERSION

    # is_installed() also requires the .ok marker: a bare chrome.exe is what an
    # interrupted extraction leaves behind, and a half-extracted build launches
    # (or crashes) without its .pak/.dat files.
    if is_installed(target_version):
        return (_cache_root() / target_version / "chrome.exe").resolve()

    if auto_install:
        return ensure_chrome(target_version).resolve()

    raise FileNotFoundError(
        "Huligan Chrome not found. Either:\n"
        f"  - pass chrome_path= to Browser()\n"
        f"  - set {env_var} environment variable\n"
        f"  - call huligan.installer.ensure_chrome() to download it"
    )
