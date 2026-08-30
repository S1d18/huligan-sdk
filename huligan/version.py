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
# Build 1 (2026-08-30): Chrome 152.0.7977.65 major bump (151 -> 152). BUILD_NUMBER
#   resets to 1 on the major. Three things beyond the version bump:
#   1. NEW .conf KEY cpu_performance_tier (CONF_SCHEMA_VERSION 1 -> 2) behind
#      Chrome 152's CPU Performance API. Derived from cpu_cores via a port of
#      Chromium's GetTierFromCores, so it can never contradict the reported core
#      count. Builds needing it carry min_conf_schema=2 in the release manifest.
#   2. TLS pins CUT to AddTLSServerHandshakePadding only. kTLSTrustAnchorIDs went
#      DISABLED_BY_DEFAULT (151) -> ENABLED_BY_DEFAULT (152) in net/base/
#      features.cc, so the 151-era pin stopped hiding an anomaly and started
#      creating one: it removed ClientHello ext 51764 that real Chrome 152 sends.
#      Measured against stock — padding-only pin matches exactly
#      (t13d1518h2_8daaf6152771_e2d80978ab2e, 20 extensions).
#   3. outer_width/outer_height are no longer emitted, and deviceMemory now goes
#      up to 32 (the 8 ceiling was Android-only and had been wrong for two
#      majors). Both were producing values real Chrome cannot report.
#
# Build 1 (2026-08-06): Chrome 151.0.7922.76 major bump (150 -> 151). BUILD_NUMBER
#   resets to 1 on the major. One real change beyond the version bump:
#   launch_plan._STEALTH_DISABLE_FEATURES gained AddTLSServerHandshakePadding.
#   On 151 a Finch seed was enabling features::kAddTLSServerHandshakePadding
#   (FEATURE_DISABLED_BY_DEFAULT in net/base/features.cc), which puts ClientHello
#   extension 4832 (0x12E0, TLSEXT_TYPE_server_padding) on the wire and moved JA4
#   t13d1517h2 -> t13d1518h2. Third Finch-flipped TLS feature in three majors.
#   Pinned off, JA4 is byte-identical to the 150 build again
#   (t13d1517h2_8daaf6152771_b6f405a00624). No new .conf key; CONF_SCHEMA_VERSION
#   untouched, so manifest min_conf_schema stays 1. No other API changes vs
#   Build 3. pyproject 1.4.0 -> 1.5.0.
# Build 3 (2026-07-18): WebUI-migration SDK helpers (Phase 2) — all public, all
#   sync-friendly so a FastAPI backend can call them without an event loop:
#   cookies.export_cookies_to_file_sync / import_cookies_from_file_sync and
#   profile_bundle.export_profile_bundle_to_file_sync (worker-thread event loop via
#   the existing persistent._BackgroundLoop; async originals unchanged),
#   proxy.test_proxy (parse + exit-IP probe + GeoIP -> one dict, never raises), and
#   geoip.resolve_launch_geo (preview the tz/lang/geolocation/webrtc a launch would
#   apply). launch_persistent's geo/tz/lang/WebRTC resolution was factored into the
#   shared geoip._resolve_geo so the preview and the real launch can never drift —
#   no behavior change on the launch path. No new .conf key; CONF_SCHEMA_VERSION
#   untouched. pyproject 1.3.0 -> 1.4.0.
# Build 2 (2026-07-15): Chrome auto-update surface + portable profile bundles.
#   Manifest-driven resolution (installer.resolve_version / channels: pinned/stable/
#   latest, TTL-cached manifest, sha from manifest), .conf compatibility gate
#   (conf_spec.CONF_SCHEMA_VERSION + IncompatibleBuildError), `huligan` CLI
#   (chrome list/update/pin/prune, version), and huligan.profile_bundle
#   (export/extract/read/write + Browser.export_profile_bundle/import_profile_bundle)
#   — one .hbundle carries fingerprint .conf + cookies. No new .conf key; schema v1.
#   pyproject 1.2.0 -> 1.3.0.
# Build 1 (2026-07-10): Chrome 150.0.7871.101 major bump (149 -> 150). BUILD_NUMBER
#   resets to 1 on the major. Binary now ships with proprietary codecs
#   (proprietary_codecs=true + ffmpeg_branding="Chrome") so H.264/AAC/MP4 play —
#   CreepJS mimes 10/12, matching real Chrome; earlier builds were open-codec-only
#   Chromium (a detectable tell). No SDK API changes vs 149 Build 3 — same
#   launch_persistent / build_launch_plan surface, no new .conf key. JA4 remains
#   t13d1517h2 (byte-identical to stock Chrome 150; TLS pins unchanged).
# Build 3 (2026-06-25): pin Finch-flippable TLS features off in launch_plan.py
#   (--disable-features=TLSTrustAnchorIDs,TlsMldsaSignatures). The variations seed
#   was flipping kTLSTrustAnchorIDs on for some sessions, adding ClientHello ext
#   0xCA34 → JA4 t13d1516h2 -> t13d1517h2, a non-Chrome TLS fingerprint WAFs
#   (SafeLine) flag. Symptom was intermittent ("works every other time") detection
#   at a stable IP. Now JA4 is deterministic. pyproject 1.1.2 -> 1.1.3.
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
BUILD_NUMBER = 1

# Patched Chrome version this SDK release expects to launch.
CHROME_VERSION = "152.0.7977.65"

# Public binary mirror used by huligan.installer.ensure_chrome().
RELEASES_REPO = "S1d18/huligan-releases"

VERSION = f"Huligan Build {BUILD_NUMBER} (Chrome {CHROME_VERSION.split('.')[0]})"
FULL_VERSION = f"huligan-{BUILD_NUMBER}-chrome-{CHROME_VERSION}"


def get_version() -> str:
    """Returns the display version string, e.g. 'Huligan Build 1 (Chrome 149)'."""
    return VERSION
