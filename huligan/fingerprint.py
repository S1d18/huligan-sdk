"""
Huligan Antidetect - Fingerprint Generator

Generates unique browser fingerprints for .conf profiles.
"""
import math
import random
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict
from pathlib import Path

from .data import get_random_gpu, get_random_resolution, get_random_fonts, get_fingerprint_params, get_extensions
from .data.gpu_vendors import pick_apple_silicon_profile


@dataclass
class FingerprintProfile:
    """Generated fingerprint profile"""

    # Screen (required fields first)
    screen_width: int
    screen_height: int
    avail_width: int
    avail_height: int

    # Hardware (required fields)
    cpu_cores: int
    device_memory: int  # GB

    # WebGL (required fields)
    webgl_vendor: str
    webgl_renderer: str

    # WebGPU (required fields)
    webgpu_vendor: str
    webgpu_architecture: str
    webgpu_device: str
    webgpu_description: str

    # Noise seeds (required fields)
    canvas_noise_seed: int
    font_noise_seed: int
    client_rects_noise_seed: int

    # Fonts (required fields)
    fonts: List[str]

    # WebGL extensions (required fields)
    webgl_extensions: List[str]
    webgl2_extensions: List[str]

    # Audio noise — disabled: BrowserScan detects noise as modified manually
    audio_noise_seed: int = 0

    # Canvas noise — OPT-IN. Default False = stable native canvas
    # (Dolphin-parity): zero tampering signal, but canvas is a stable
    # cross-site fingerprint shared across profiles on the same host.
    # Set True only when you need per-profile canvas unlinkability — the
    # C++ patch then applies the v2 sparse algorithm (<=10 pixels, stays
    # clean on BrowserScan). canvas_noise_seed is always populated
    # regardless (it also seeds media-device IDs); this flag only gates
    # whether the browser actually perturbs the canvas.
    canvas_noise_enabled: bool = False

    # Screen (optional fields with defaults)
    color_depth: int = 24
    device_pixel_ratio: float = 1.0
    outer_width: int = 0
    outer_height: int = 0

    # Hardware (optional fields with defaults)
    platform: str = "Win32"
    max_touch_points: int = 0

    # Languages (placeholder, will be set by GeoIP)
    languages: str = "en-US,en"

    # Geolocation (placeholder, will be set by GeoIP)
    geolocation_latitude: float = 0.0
    geolocation_longitude: float = 0.0
    geolocation_accuracy: int = 100

    # Timezone (placeholder, will be set by GeoIP)
    timezone: str = "America/New_York"

    # Media devices
    media_devices_video_input_label: str = "HD WebCam"
    media_devices_audio_input_label: str = "Microphone (HD WebCam)"
    media_devices_audio_output_label: str = "Speakers (High Definition Audio)"

    # Battery
    battery_enabled: bool = True
    battery_charging: bool = True
    battery_level: float = 1.0
    battery_charging_time: int = 0
    battery_discharging_time: float = float('inf')

    # Connection
    connection_type: str = "ethernet"  # ethernet, wifi, cellular, none, other (matches GUI Profile)
    connection_downlink: float = 10.0
    connection_effective_type: str = "4g"
    connection_rtt: int = 50
    connection_save_data: bool = False

    # Extra
    do_not_track: bool = False
    block_port_scan: bool = True
    history_length_min: int = 2

    # Audio properties (read by patch 09_audio — were previously NOT serialized
    # by to_conf, so SDK-generated profiles lacked them vs the reference conf).
    audio_sample_rate: int = 44100
    audio_max_channel_count: int = 2
    audio_base_latency: float = 0.01
    audio_output_latency: float = 0.02

    # matchMedia prefers-color-scheme. Default "dark" avoids the CreepJS
    # "prefersLightColor: true" headless tell (PARAMETER_MAPPING.md).
    preferred_color_scheme: str = "dark"

    # CDP stealth mode. "paranoid" (default) blocks Runtime.enable /
    # Console.enable / Debugger.enable evaluate surfaces so page JS
    # cannot detect CDP; page.evaluate is effectively unusable.
    # "isolated" disables those three suppressions so the upstream
    # agents framework / Playwright can drive Runtime.evaluate
    # normally, while every other CDP hardening (json endpoint
    # hiding, screenX/Y fix, stack-trace filter, etc.) stays on.
    # Browser.start() forwards this as HULIGAN_CDP_MODE env var.
    cdp_mode: str = "paranoid"

    # WebRTC spoof — values written into ICE candidates by the C++
    # patch in third_party/webrtc/p2p/base/port.cc (see huligan-browser
    # patches/chromium/11a_webrtc_spoof.py). When non-empty, page JS
    # observes these as the local addresses in RTCIceCandidate.
    # Browser.start() auto-fills webrtc_local_ipv4 from the proxy exit
    # IP detected via huligan.proxy.detect_exit_ip(); manual values
    # set on the profile take precedence. Leave empty to pass that
    # IP family through unchanged.
    webrtc_local_ipv4: str = ""
    webrtc_local_ipv6: str = ""

    # V8/ICU native locale spoof (huligan-browser
    # patches/chromium/17_locale.py). Drives the "default" locale that
    # Intl.DateTimeFormat / Collator / NumberFormat fall back to, and
    # the Accept-Language HTTP header. Empty = let upstream Chromium
    # pick from the host OS locale. The patch reads this key as
    # intl_locale=; languages= is read separately.
    intl_locale: str = ""

    # WebGPU adapter limits / features / subgroup sizes
    # (huligan-browser patches/chromium/10_webgpu.py v2). Empty values
    # = passthrough (the patched binary keeps whatever the underlying
    # adapter exposes). Set together with webgl_renderer for an
    # internally-consistent GPU class.
    #
    # Note: the navigator.deviceMemory cap of 8 GB does NOT apply here
    # — these are raw numbers from the WebGPU spec.
    webgpu_max_buffer_size: int = 0                       # bytes; 0 = passthrough
    webgpu_max_storage_buffer_binding_size: int = 0       # bytes
    webgpu_max_compute_workgroup_size_x: int = 0
    webgpu_max_compute_workgroup_size_y: int = 0
    webgpu_max_compute_workgroup_size_z: int = 0
    webgpu_features: List[str] = field(default_factory=list)  # complete set, not delta
    webgpu_subgroup_min_size: int = 0
    webgpu_subgroup_max_size: int = 0

    # Optional directory of operator-supplied .ttf/.otf fonts. When
    # non-empty, the patched Chromium registers every font file in
    # this directory process-locally before any enumeration runs,
    # so canvas / WebGL glyph rendering matches the OS the UA claims.
    # Recommended fillers (Apache 2.0 / SIL OFL — no proprietary
    # MS/Apple fonts): Noto Color Emoji, Noto Sans CJK, DejaVu,
    # Liberation. See NOTICE.md for the licensing matrix.
    fonts_dir: str = ""

    # WebGL parameters (GL enum -> value, auto-populated from GPU)
    webgl_params: Dict[int, object] = field(default_factory=dict)

    @classmethod
    def from_seed(
        cls,
        seed: int,
        *,
        platform: str = "Win32",
        gpu_vendor_preference: Optional[str] = None,
        canvas_noise: bool = False,
    ) -> "FingerprintProfile":
        """
        Build a deterministic profile from a single integer seed.

        Same seed + same SDK major version => same profile. Quick path for
        users who don't want to specify all 50+ fields manually.
        ``audio_noise_seed=0`` is enforced regardless of seed (BrowserScan
        flags any non-zero audio noise as "Audio modified manually").

        Args:
            seed: Any non-negative integer. Internally sha256-hashed, so
                values larger than 2**64 are supported.
            platform: ``"Win32"``, ``"MacIntel"``, or ``"Linux x86_64"``.
                Defaults to Win32 (highest population share).
            gpu_vendor_preference: ``"nvidia"``, ``"amd"``, ``"intel"``,
                or ``None`` to let the seed pick.

        Returns:
            FingerprintProfile ready to ``.to_conf()`` and pass to
            ``Browser(profile_path=...)``.

        Example:
            >>> profile = FingerprintProfile.from_seed(12345)
            >>> Path("p.conf").write_text(profile.to_conf())
        """
        return FingerprintGenerator(seed=seed).generate(
            platform=platform,
            gpu_vendor_preference=gpu_vendor_preference,
            canvas_noise=canvas_noise,
        )

    @classmethod
    def template(
        cls,
        name: str,
        seed: Optional[int] = None,
    ) -> "FingerprintProfile":
        """
        Build a profile from a curated named preset.

        Combines ``from_seed`` (for the random-but-deterministic fields:
        fonts, noise seeds, media-device IDs, etc.) with template-specific
        overrides (timezone, GPU, screen, language, hardware specs).

        ``audio_noise_seed=0`` is preserved by the underlying ``from_seed``
        contract — templates never touch it.

        Args:
            name: Template key. See ``huligan.templates.TEMPLATES`` or
                ``huligan.templates.list_templates()``.
            seed: Optional deterministic seed. ``None`` draws a random
                64-bit value so each call produces a distinct identity
                under the same template.

        Returns:
            FingerprintProfile with template overrides applied.

        Raises:
            KeyError: If ``name`` is not a known template.

        Example:
            >>> p = FingerprintProfile.template("usa_verified_facebook", seed=42)
            >>> p.timezone
            'America/New_York'
        """
        # Local import keeps templates as an optional, low-coupling module.
        from .templates import TEMPLATES

        if name not in TEMPLATES:
            available = ", ".join(sorted(TEMPLATES))
            raise KeyError(
                f"Unknown template {name!r}. Available templates: {available}"
            )

        if seed is None:
            seed = secrets.randbits(64)

        spec = TEMPLATES[name]
        profile = cls.from_seed(seed, **spec.get("from_seed_kwargs", {}))

        overrides = spec.get("overrides", {})
        for attr, value in overrides.items():
            if not hasattr(profile, attr):
                raise AttributeError(
                    f"Template {name!r} sets unknown attribute {attr!r}"
                )
            setattr(profile, attr, value)

        # WebGL params / extensions are derived from the renderer string.
        # When a template overrides the renderer, refresh both so the
        # profile stays internally consistent.
        if "webgl_renderer" in overrides:
            profile.webgl_params = get_fingerprint_params(profile.webgl_renderer)
            profile.webgl_extensions = get_extensions(profile.webgl_renderer, webgl_version=1)
            profile.webgl2_extensions = get_extensions(profile.webgl_renderer, webgl_version=2)

        return profile

    def to_conf(self) -> str:
        """Convert to .conf file format via the canonical serializer.

        Delegates to :func:`huligan.conf_spec.render_conf` (the single source of
        truth for key names + formats) so the SDK and the desktop app cannot
        drift. Output is the same contract as before plus the audio properties
        and ``preferred_color_scheme`` that the binary reads but the old
        hand-written serializer omitted.
        """
        from .conf_spec import render_conf, default_media_devices

        media_devices = default_media_devices(
            self.canvas_noise_seed,
            audio_in_label=self.media_devices_audio_input_label,
            audio_out_label=self.media_devices_audio_output_label,
            video_label=self.media_devices_video_input_label,
        )
        cdp_mode = self.cdp_mode if self.cdp_mode in ("paranoid", "isolated") else "paranoid"

        values = {
            # Screen
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "screen_avail_width": self.avail_width,
            "screen_avail_height": self.avail_height,
            "outer_width": self.outer_width,
            "outer_height": self.outer_height,
            "color_depth": self.color_depth,
            "device_pixel_ratio": self.device_pixel_ratio,
            "pixel_depth": self.color_depth,
            "screen_avail_left": 0,
            "screen_avail_top": 0,
            # Hardware
            "cpu_cores": self.cpu_cores,
            "device_memory": self.device_memory,
            "platform": self.platform,
            "max_touch_points": self.max_touch_points,
            # WebGL
            "webgl_vendor": self.webgl_vendor,
            "webgl_renderer": self.webgl_renderer,
            "webgl_extensions": self.webgl_extensions,
            "webgl2_extensions": self.webgl2_extensions,
            "webgl_params": self.webgl_params,
            # WebGPU
            "webgpu_vendor": self.webgpu_vendor,
            "webgpu_architecture": self.webgpu_architecture,
            "webgpu_device": self.webgpu_device,
            "webgpu_description": self.webgpu_description,
            "webgpu_max_buffer_size": self.webgpu_max_buffer_size,
            "webgpu_max_storage_buffer_binding_size": self.webgpu_max_storage_buffer_binding_size,
            "webgpu_max_compute_workgroup_size_x": self.webgpu_max_compute_workgroup_size_x,
            "webgpu_max_compute_workgroup_size_y": self.webgpu_max_compute_workgroup_size_y,
            "webgpu_max_compute_workgroup_size_z": self.webgpu_max_compute_workgroup_size_z,
            "webgpu_features": self.webgpu_features,
            "webgpu_subgroup_min_size": self.webgpu_subgroup_min_size,
            "webgpu_subgroup_max_size": self.webgpu_subgroup_max_size,
            "webgpu_enabled": True,
            # Noise
            "canvas_noise_seed": self.canvas_noise_seed,
            "canvas_noise_enabled": self.canvas_noise_enabled,
            "audio_noise_seed": 0,
            "font_noise_seed": self.font_noise_seed,
            "client_rects_noise_seed": self.client_rects_noise_seed,
            # Audio
            "audio_sample_rate": self.audio_sample_rate,
            "audio_max_channel_count": self.audio_max_channel_count,
            "audio_base_latency": self.audio_base_latency,
            "audio_output_latency": self.audio_output_latency,
            # Fonts
            "fonts": self.fonts,
            "fonts_dir": self.fonts_dir,
            # Geo
            "languages": self.languages,
            "intl_locale": self.intl_locale,
            "geolocation_latitude": self.geolocation_latitude,
            "geolocation_longitude": self.geolocation_longitude,
            "geolocation_accuracy": self.geolocation_accuracy,
            "timezone": self.timezone,
            # Media
            "media_devices": media_devices,
            # Battery
            "battery_enabled": self.battery_enabled,
            "battery_charging": self.battery_charging,
            "battery_level": self.battery_level,
            "battery_charging_time": self.battery_charging_time,
            "battery_discharging_time": self.battery_discharging_time,
            # Connection
            "connection_type": self.connection_type,
            "connection_downlink": self.connection_downlink,
            "connection_effective_type": self.connection_effective_type,
            "connection_rtt": self.connection_rtt,
            "connection_save_data": self.connection_save_data,
            # Extra
            "do_not_track": self.do_not_track,
            "block_port_scan": self.block_port_scan,
            "history_length_min": self.history_length_min,
            "preferred_color_scheme": self.preferred_color_scheme,
            # CDP stealth
            "cdp_mode": cdp_mode,
            "cdp_stealth": True,
            "cdp_hide_json_endpoint": True,
            "cdp_filter_stack_traces": True,
            "cdp_suppress_console_replay": True,
            "cdp_suppress_script_enum": True,
            "cdp_normalize_timing": True,
            "cdp_fix_screen_coords": True,
            # WebRTC
            "webrtc_block": True,
            "webrtc_local_ipv4": self.webrtc_local_ipv4,
            "webrtc_local_ipv6": self.webrtc_local_ipv6,
        }
        return render_conf(values, header="Huligan Antidetect Profile - Auto-generated")

    def to_json(self) -> str:
        """Convert to JSON format"""
        data = {}

        data["screen_width"] = self.screen_width
        data["screen_height"] = self.screen_height
        data["screen_avail_width"] = self.avail_width
        data["screen_avail_height"] = self.avail_height
        data["outer_width"] = self.outer_width
        data["outer_height"] = self.outer_height
        data["color_depth"] = self.color_depth
        data["device_pixel_ratio"] = self.device_pixel_ratio

        data["cpu_cores"] = self.cpu_cores
        data["device_memory"] = self.device_memory
        data["platform"] = self.platform
        data["max_touch_points"] = self.max_touch_points

        data["webgl_vendor"] = self.webgl_vendor
        data["webgl_renderer"] = self.webgl_renderer
        data["webgl_extensions"] = self.webgl_extensions
        data["webgl2_extensions"] = self.webgl2_extensions

        data["webgpu_vendor"] = self.webgpu_vendor
        data["webgpu_architecture"] = self.webgpu_architecture
        data["webgpu_device"] = self.webgpu_device
        data["webgpu_description"] = self.webgpu_description

        data["canvas_noise_seed"] = self.canvas_noise_seed
        data["canvas_noise_enabled"] = self.canvas_noise_enabled
        data["audio_noise_seed"] = self.audio_noise_seed
        data["font_noise_seed"] = self.font_noise_seed
        data["client_rects_noise_seed"] = self.client_rects_noise_seed

        data["fonts"] = self.fonts

        data["languages"] = self.languages
        data["geolocation_latitude"] = self.geolocation_latitude
        data["geolocation_longitude"] = self.geolocation_longitude
        data["geolocation_accuracy"] = self.geolocation_accuracy
        data["timezone"] = self.timezone

        data["media_devices_video_input_label"] = self.media_devices_video_input_label
        data["media_devices_audio_input_label"] = self.media_devices_audio_input_label
        data["media_devices_audio_output_label"] = self.media_devices_audio_output_label

        data["battery_charging"] = self.battery_charging
        data["battery_level"] = self.battery_level
        data["battery_charging_time"] = self.battery_charging_time
        data["battery_discharging_time"] = "inf" if math.isinf(self.battery_discharging_time) else int(self.battery_discharging_time)

        data["connection_downlink"] = self.connection_downlink
        data["connection_effective_type"] = self.connection_effective_type
        data["connection_rtt"] = self.connection_rtt
        data["connection_save_data"] = self.connection_save_data

        data["do_not_track"] = self.do_not_track
        data["block_port_scan"] = self.block_port_scan
        data["history_length_min"] = self.history_length_min

        if self.webgl_params:
            for gl_enum, value in sorted(self.webgl_params.items()):
                data[f"webgl_param_{gl_enum}"] = value

        return json.dumps(data, indent=2)


class FingerprintGenerator:
    """Generate unique browser fingerprints"""

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize generator.

        Args:
            seed: Random seed for reproducibility (optional)
        """
        self.seed = seed
        self.rng = random.Random(seed)

    def generate(
        self,
        platform: str = "Win32",
        gpu_vendor_preference: Optional[str] = None,
        canvas_noise: bool = False,
    ) -> FingerprintProfile:
        """
        Generate unique fingerprint profile.

        Args:
            platform: "Win32", "MacIntel", or "Linux x86_64"
            gpu_vendor_preference: "nvidia", "amd", "intel", or None
            canvas_noise: opt-in per-profile canvas. Default False =
                stable native canvas (Dolphin-parity, zero tampering
                signal). True = unique-but-clean canvas via the v2
                sparse algorithm (use when canvas unlinkability matters).

        Returns:
            FingerprintProfile
        """
        width, height, avail_w, avail_h, dpr = get_random_resolution(self.rng)

        # Default hardware spec — overridden below for MacIntel so the
        # chip / cores / RAM stay internally consistent (fixes the
        # cluster effect documented in CloakBrowser #236).
        cpu_cores = self.rng.choice([2, 4, 4, 6, 6, 8, 8])
        device_memory = self.rng.choice([2, 4, 8, 8, 8])

        max_touch_points = 0 if platform == "Win32" else self.rng.choice([0, 5, 10])

        if platform == "MacIntel":
            chip, mac_cores, mac_real_ram = pick_apple_silicon_profile(self.rng)
            vendor = "Google Inc. (Apple)"
            renderer = f"ANGLE (Apple, ANGLE Metal Renderer: Apple {chip}, Unspecified Version)"
            device_id = chip
            cpu_cores = mac_cores
            # navigator.deviceMemory caps at 8 per spec — keep the
            # spec-visible value here; real RAM is preserved in the
            # tuple if a future channel ever needs it.
            device_memory = min(mac_real_ram, 8)
        else:
            vendor, renderer, device_id = get_random_gpu(
                gpu_vendor_preference, self.rng, platform=platform
            )

        if "Apple" in vendor:
            webgpu_vendor = "apple"
            webgpu_arch = "apple-silicon"
        elif "NVIDIA" in vendor:
            webgpu_vendor = "nvidia"
            webgpu_arch = "ampere" if "RTX 40" in renderer or "RTX 30" in renderer else "turing"
        elif "AMD" in vendor:
            webgpu_vendor = "amd"
            webgpu_arch = "rdna3" if "RX 7" in renderer else "rdna2"
        else:
            webgpu_vendor = "intel"
            webgpu_arch = "xe"

        if self.seed is None:
            base_seed = int(time.time() * 1000000)
        else:
            h = hashlib.sha256(f"{self.seed}".encode()).digest()
            base_seed = int.from_bytes(h[:8], 'big')

        canvas_seed = (base_seed + 0x1111) & 0xFFFFFFFF
        # audio_noise_seed is always 0 — disabled: BrowserScan detects noise as modified manually
        font_seed = (base_seed + 0x3333) & 0xFFFFFFFF
        client_rects_seed = (base_seed + 0x4444) & 0xFFFFFFFF

        fonts = get_random_fonts(platform, count=None, rng=self.rng)

        webgl_params = get_fingerprint_params(renderer)
        webgl_exts = get_extensions(renderer, webgl_version=1)
        webgl2_exts = get_extensions(renderer, webgl_version=2)

        webcam_models = ["HD WebCam", "FaceTime HD Camera", "Integrated Camera", "USB Camera"]
        mic_models = ["Microphone (HD WebCam)", "Internal Microphone", "USB Microphone"]
        speaker_models = ["Speakers (High Definition Audio)", "Internal Speakers", "Headphones"]

        return FingerprintProfile(
            screen_width=width,
            screen_height=height,
            avail_width=avail_w,
            avail_height=avail_h,
            outer_width=width,
            outer_height=height,
            device_pixel_ratio=dpr,
            cpu_cores=cpu_cores,
            device_memory=device_memory,
            platform=platform,
            max_touch_points=max_touch_points,
            webgl_vendor=vendor,
            webgl_renderer=renderer,
            webgpu_vendor=webgpu_vendor,
            webgpu_architecture=webgpu_arch,
            webgpu_device=renderer,
            webgpu_description=f"{renderer} ({device_id})",
            canvas_noise_seed=canvas_seed,
            canvas_noise_enabled=canvas_noise,
            font_noise_seed=font_seed,
            client_rects_noise_seed=client_rects_seed,
            fonts=fonts,
            webgl_extensions=webgl_exts,
            webgl2_extensions=webgl2_exts,
            media_devices_video_input_label=self.rng.choice(webcam_models),
            media_devices_audio_input_label=self.rng.choice(mic_models),
            media_devices_audio_output_label=self.rng.choice(speaker_models),
            webgl_params=webgl_params,
        )

    def generate_to_file(self, output_path: Path, **kwargs) -> FingerprintProfile:
        """
        Generate profile and save to file.
        Auto-detects format by extension: .json for JSON, .conf for key=value.

        Args:
            output_path: Path to save file (.conf or .json)
            **kwargs: Passed to generate()

        Returns:
            FingerprintProfile
        """
        profile = self.generate(**kwargs)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if str(output_path).endswith('.json'):
            output_path.write_text(profile.to_json())
        else:
            output_path.write_text(profile.to_conf())
        return profile
