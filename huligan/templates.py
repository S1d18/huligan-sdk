"""
Curated, named profile presets for huligan-sdk.

Each template is a small kwargs dict that overrides specific
fingerprint fields after a deterministic ``from_seed`` build, so
non-power users can spin up a realistic identity in one line.

The ``audio_noise_seed=0`` invariant is preserved end-to-end by
delegating field assembly to ``FingerprintProfile.from_seed``.
"""
from typing import Dict, List, Tuple


# Each template carries:
#   from_seed_kwargs: passed straight to FingerprintProfile.from_seed
#   overrides:        attributes to set on the returned profile,
#                     including a fully-formed ANGLE renderer string.
# WebGL extensions / params are recomputed downstream from the
# overridden renderer so the profile stays internally consistent.
TEMPLATES: Dict[str, Dict] = {
    "usa_verified_facebook": {
        "from_seed_kwargs": {
            "platform": "Win32",
            "gpu_vendor_preference": "nvidia",
        },
        "overrides": {
            "screen_width": 1920,
            "screen_height": 1080,
            "avail_width": 1920,
            "avail_height": 1040,
            "outer_width": 1920,
            "outer_height": 1080,
            "device_pixel_ratio": 1.0,
            "cpu_cores": 8,
            "device_memory": 8,
            "platform": "Win32",
            "max_touch_points": 0,
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": (
                "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002503) "
                "Direct3D11 vs_5_0 ps_5_0, D3D11)"
            ),
            "webgpu_vendor": "nvidia",
            "webgpu_architecture": "ampere",
            "webgpu_device": "GeForce RTX 3060",
            "webgpu_description": "GeForce RTX 3060 (0x00002503)",
            "timezone": "America/New_York",
            "languages": "en-US,en",
            "geolocation_latitude": 40.7128,
            "geolocation_longitude": -74.0060,
            "geolocation_accuracy": 100,
        },
    },
    "usa_office_chrome": {
        "from_seed_kwargs": {
            "platform": "Win32",
            "gpu_vendor_preference": "intel",
        },
        "overrides": {
            "screen_width": 1920,
            "screen_height": 1080,
            "avail_width": 1920,
            "avail_height": 1040,
            "outer_width": 1920,
            "outer_height": 1080,
            "device_pixel_ratio": 1.0,
            "cpu_cores": 4,
            "device_memory": 8,
            "platform": "Win32",
            "max_touch_points": 0,
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": (
                "ANGLE (Intel, Intel(R) UHD Graphics 770 (0x00004680) "
                "Direct3D11 vs_5_0 ps_5_0, D3D11)"
            ),
            "webgpu_vendor": "intel",
            "webgpu_architecture": "xe",
            "webgpu_device": "UHD Graphics 770",
            "webgpu_description": "UHD Graphics 770 (0x00004680)",
            "timezone": "America/Chicago",
            "languages": "en-US,en",
            "geolocation_latitude": 41.8781,
            "geolocation_longitude": -87.6298,
            "geolocation_accuracy": 100,
        },
    },
    "eu_mobile_twitter": {
        "from_seed_kwargs": {
            "platform": "Win32",
            "gpu_vendor_preference": "intel",
        },
        "overrides": {
            "screen_width": 1536,
            "screen_height": 864,
            "avail_width": 1536,
            "avail_height": 824,
            "outer_width": 1536,
            "outer_height": 864,
            "device_pixel_ratio": 1.25,
            "cpu_cores": 4,
            "device_memory": 8,
            "platform": "Win32",
            "max_touch_points": 0,
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": (
                "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) "
                "Direct3D11 vs_5_0 ps_5_0, D3D11)"
            ),
            "webgpu_vendor": "intel",
            "webgpu_architecture": "xe",
            "webgpu_device": "Iris(R) Xe Graphics",
            "webgpu_description": "Iris(R) Xe Graphics (0x00009A49)",
            "timezone": "Europe/Berlin",
            "languages": "de-DE,de,en-US;q=0.9,en;q=0.8",
            "geolocation_latitude": 52.5200,
            "geolocation_longitude": 13.4050,
            "geolocation_accuracy": 100,
        },
    },
    "apac_crypto_exchange": {
        "from_seed_kwargs": {
            "platform": "Win32",
            "gpu_vendor_preference": "nvidia",
        },
        "overrides": {
            "screen_width": 2560,
            "screen_height": 1440,
            "avail_width": 2560,
            "avail_height": 1400,
            "outer_width": 2560,
            "outer_height": 1440,
            "device_pixel_ratio": 1.0,
            "cpu_cores": 12,
            "device_memory": 8,
            "platform": "Win32",
            "max_touch_points": 0,
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": (
                "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 (0x00002484) "
                "Direct3D11 vs_5_0 ps_5_0, D3D11)"
            ),
            "webgpu_vendor": "nvidia",
            "webgpu_architecture": "ampere",
            "webgpu_device": "GeForce RTX 3070",
            "webgpu_description": "GeForce RTX 3070 (0x00002484)",
            "timezone": "Asia/Singapore",
            "languages": "en-US,en",
            "geolocation_latitude": 1.3521,
            "geolocation_longitude": 103.8198,
            "geolocation_accuracy": 100,
        },
    },
    "latam_casual_browsing": {
        "from_seed_kwargs": {
            "platform": "Win32",
            "gpu_vendor_preference": "amd",
        },
        "overrides": {
            "screen_width": 1366,
            "screen_height": 768,
            "avail_width": 1366,
            "avail_height": 728,
            "outer_width": 1366,
            "outer_height": 768,
            "device_pixel_ratio": 1.0,
            "cpu_cores": 6,
            "device_memory": 8,
            "platform": "Win32",
            "max_touch_points": 0,
            "webgl_vendor": "Google Inc. (AMD)",
            "webgl_renderer": (
                "ANGLE (AMD, AMD Radeon RX 5600 XT (0x0000731F) "
                "Direct3D11 vs_5_0 ps_5_0, D3D11)"
            ),
            "webgpu_vendor": "amd",
            "webgpu_architecture": "rdna1",
            "webgpu_device": "Radeon RX 5600 XT",
            "webgpu_description": "Radeon RX 5600 XT (0x0000731F)",
            "timezone": "America/Mexico_City",
            "languages": "es-MX,es,en-US;q=0.9,en;q=0.8",
            "geolocation_latitude": 19.4326,
            "geolocation_longitude": -99.1332,
            "geolocation_accuracy": 100,
        },
    },
    "macos_developer": {
        "from_seed_kwargs": {
            "platform": "MacIntel",
            "gpu_vendor_preference": None,
        },
        "overrides": {
            "screen_width": 2560,
            "screen_height": 1440,
            "avail_width": 2560,
            "avail_height": 1410,
            "outer_width": 2560,
            "outer_height": 1440,
            "device_pixel_ratio": 2.0,
            "cpu_cores": 8,
            "device_memory": 8,
            "platform": "MacIntel",
            "max_touch_points": 0,
            "webgl_vendor": "Google Inc. (Apple)",
            "webgl_renderer": (
                "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, "
                "Unspecified Version)"
            ),
            "webgpu_vendor": "apple",
            "webgpu_architecture": "apple-silicon",
            "webgpu_device": "Apple M2",
            "webgpu_description": "Apple M2 GPU",
            "timezone": "America/Los_Angeles",
            "languages": "en-US,en",
            "geolocation_latitude": 37.7749,
            "geolocation_longitude": -122.4194,
            "geolocation_accuracy": 100,
            "media_devices_video_input_label": "FaceTime HD Camera",
            "media_devices_audio_input_label": "MacBook Pro Microphone",
            "media_devices_audio_output_label": "MacBook Pro Speakers",
        },
    },
}


TEMPLATE_DESCRIPTIONS: Dict[str, str] = {
    "usa_verified_facebook": (
        "US Windows desktop, NVIDIA RTX 3060, 1920x1080, en-US, "
        "America/New_York, 8 cores / 8 GB."
    ),
    "usa_office_chrome": (
        "US office worker, Intel UHD 770, 1920x1080, en-US, "
        "America/Chicago, 4 cores / 8 GB."
    ),
    "eu_mobile_twitter": (
        "EU mid-range laptop (Win32, Intel Iris Xe), 1536x864, de-DE, "
        "Europe/Berlin, 4 cores / 8 GB."
    ),
    "apac_crypto_exchange": (
        "APAC gaming workstation, NVIDIA RTX 3070, 2560x1440, en-US, "
        "Asia/Singapore, 12 cores / 8 GB."
    ),
    "latam_casual_browsing": (
        "LatAm modest hardware, AMD RX 5600 XT, 1366x768, es-MX, "
        "America/Mexico_City, 6 cores / 8 GB."
    ),
    "macos_developer": (
        "macOS dev box, Apple M2, 2560x1440 @2x, en-US, "
        "America/Los_Angeles, 8 cores / 8 GB."
    ),
}


def list_templates() -> List[Tuple[str, str]]:
    """Return ``[(name, one-line description), ...]`` for all templates."""
    return [(name, TEMPLATE_DESCRIPTIONS[name]) for name in TEMPLATES]
