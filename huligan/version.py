"""Huligan Antidetect — version metadata.

The SDK does NOT carry GREASE brand / XBV hash / spoofed UA constants:
those live inside the patched Chrome binary itself. This module only
holds the version string used by the installer to pick the right release
from the public binary mirror.
"""

# Internal build counter — bumped whenever the SDK is republished against
# the same Chrome version (bug fixes, doc updates, dependency changes).
BUILD_NUMBER = 3

# Patched Chrome version this SDK release expects to launch.
CHROME_VERSION = "147.0.7727.56"

# Public binary mirror used by huligan.installer.ensure_chrome().
RELEASES_REPO = "S1d18/huligan-releases"

VERSION = f"Huligan Build {BUILD_NUMBER} (Chrome {CHROME_VERSION.split('.')[0]})"
FULL_VERSION = f"huligan-{BUILD_NUMBER}-chrome-{CHROME_VERSION}"


def get_version() -> str:
    """Returns display version string like 'Huligan Build 2 (Chrome 147)'."""
    return VERSION
