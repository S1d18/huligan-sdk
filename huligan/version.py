"""Huligan Antidetect — version metadata.

The SDK does NOT carry GREASE brand / XBV hash / spoofed UA constants:
those live inside the patched Chrome binary itself. This module only
holds the version string used by the installer to pick the right release
from the public binary mirror.
"""

# Internal build counter — bumped whenever the SDK is republished against
# the same Chrome version (bug fixes, doc updates, dependency changes).
# Resets to 1 on each Chrome major bump.
#
# Build 2 (2026-06-08): canonical .conf serializer (huligan.conf_spec) — one source
#   of truth shared by FingerprintProfile.to_conf AND the app's GUI Profile, so SDK-
#   and GUI-made profiles emit an identical, complete .conf (fixes the 2026-06-05
#   .conf-key drift bug). Added battery_enabled + connection_type (SDK<->GUI parity) +
#   audio_* + preferred_color_scheme. pyproject 1.1.1 -> 1.1.2.
# Build 1 (2026-06-08): Chrome 149.0.7827.54 major bump (148 -> 149). BUILD_NUMBER
#   resets to 1 on the major. No SDK API changes vs Build 5 — same
#   launch_persistent / LaunchResult / build_launch_plan surface; no new .conf key.
# Build 5 (2026-06-05): public sync persistent-launch API
#   (huligan.launch_persistent / LaunchResult / LaunchSession), shared
#   build_launch_plan, and cookies attach-by-port helpers. Lets the desktop GUI
#   delegate all browser/proxy/leak-flag/GeoIP launch logic to the SDK.
BUILD_NUMBER = 2

# Patched Chrome version this SDK release expects to launch.
CHROME_VERSION = "149.0.7827.54"

# Public binary mirror used by huligan.installer.ensure_chrome().
RELEASES_REPO = "S1d18/huligan-releases"

VERSION = f"Huligan Build {BUILD_NUMBER} (Chrome {CHROME_VERSION.split('.')[0]})"
FULL_VERSION = f"huligan-{BUILD_NUMBER}-chrome-{CHROME_VERSION}"


def get_version() -> str:
    """Returns the display version string, e.g. 'Huligan Build 1 (Chrome 149)'."""
    return VERSION
