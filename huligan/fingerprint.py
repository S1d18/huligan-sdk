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
    battery_charging: bool = True
    battery_level: float = 1.0
    battery_charging_time: int = 0
    battery_discharging_time: float = float('inf')

    # Connection
    connection_downlink: float = 10.0
    connection_effective_type: str = "4g"
    connection_rtt: int = 50
    connection_save_data: bool = False

    # Extra
    do_not_track: bool = False
    block_port_scan: bool = True
    history_length_min: int = 2

    # CDP stealth mode. "paranoid" (default) blocks Runtime.enable /
    # Console.enable / Debugger.enable evaluate surfaces so page JS
    # cannot detect CDP; page.evaluate is effectively unusable.
    # "isolated" disables those three suppressions so the upstream
    # agents framework / Playwright can drive Runtime.evaluate
    # normally, while every other CDP hardening (json endpoint
    # hiding, screenX/Y fix, stack-trace filter, etc.) stays on.
    # Browser.start() forwards this as HULIGAN_CDP_MODE env var.
    cdp_mode: str = "paranoid"

    # WebGL parameters (GL enum -> value, auto-populated from GPU)
    webgl_params: Dict[int, object] = field(default_factory=dict)

    @classmethod
    def from_seed(
        cls,
        seed: int,
        *,
        platform: str = "Win32",
        gpu_vendor_preference: Optional[str] = None,
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
        """Convert to .conf file format"""
        lines = []
        lines.append("# Huligan Antidetect Profile - Auto-generated")
        lines.append(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Screen
        lines.append("# Screen")
        lines.append(f"screen_width={self.screen_width}")
        lines.append(f"screen_height={self.screen_height}")
        lines.append(f"screen_avail_width={self.avail_width}")
        lines.append(f"screen_avail_height={self.avail_height}")
        lines.append(f"outer_width={self.outer_width}")
        lines.append(f"outer_height={self.outer_height}")
        lines.append(f"color_depth={self.color_depth}")
        lines.append(f"device_pixel_ratio={self.device_pixel_ratio}")
        lines.append("")

        # Hardware
        lines.append("# Hardware")
        lines.append(f"cpu_cores={self.cpu_cores}")
        lines.append(f"device_memory={self.device_memory}")
        lines.append(f"platform={self.platform}")
        lines.append(f"max_touch_points={self.max_touch_points}")
        lines.append("")

        # WebGL
        lines.append("# WebGL")
        lines.append(f"webgl_vendor={self.webgl_vendor}")
        lines.append(f"webgl_renderer={self.webgl_renderer}")
        if self.webgl_extensions:
            lines.append(f"webgl_extensions={','.join(self.webgl_extensions)}")
        if self.webgl2_extensions:
            lines.append(f"webgl2_extensions={','.join(self.webgl2_extensions)}")
        if self.webgl_params:
            lines.append("# WebGL Parameters (GL enum -> value)")
            for gl_enum, value in sorted(self.webgl_params.items()):
                if isinstance(value, list):
                    lines.append(f"webgl_param_{gl_enum}={','.join(str(v) for v in value)}")
                else:
                    lines.append(f"webgl_param_{gl_enum}={value}")
        lines.append("")

        # WebGPU
        lines.append("# WebGPU")
        lines.append(f"webgpu_vendor={self.webgpu_vendor}")
        lines.append(f"webgpu_architecture={self.webgpu_architecture}")
        lines.append(f"webgpu_device={self.webgpu_device}")
        lines.append(f"webgpu_description={self.webgpu_description}")
        lines.append("")

        # Noise
        lines.append("# Noise Seeds")
        lines.append(f"canvas_noise_seed={self.canvas_noise_seed}")
        lines.append(f"canvas_noise_enabled=true")
        lines.append(f"audio_noise_seed=0")  # Disabled: BrowserScan detects audio noise as "modified manually"
        lines.append(f"font_noise_seed={self.font_noise_seed}")
        lines.append(f"client_rects_noise_seed={self.client_rects_noise_seed}")
        lines.append("")

        # Fonts
        lines.append("# Fonts")
        lines.append(f"fonts={','.join(self.fonts)}")
        lines.append("")

        # Geo
        lines.append("# Geolocation")
        lines.append(f"languages={self.languages}")
        lines.append(f"geolocation_latitude={self.geolocation_latitude}")
        lines.append(f"geolocation_longitude={self.geolocation_longitude}")
        lines.append(f"geolocation_accuracy={self.geolocation_accuracy}")
        lines.append(f"timezone={self.timezone}")
        lines.append("")

        # Media Devices — format matches what 12_media_devices.py C++ patch reads
        seed_str = str(self.canvas_noise_seed)
        def _mid(suffix):
            return hashlib.sha256(f"{seed_str}_{suffix}".encode()).hexdigest()

        audio_in_did  = _mid("audio_in_device")
        audio_grp_id  = _mid("audio_group")
        audio_out_did = _mid("audio_out_device")
        video_did     = _mid("video_device")
        video_grp_id  = _mid("video_group")

        lines.append("# Media Devices")
        lines.append("media_devices_count=3")
        lines.append("media_device_0_kind=audioinput")
        lines.append(f"media_device_0_label={self.media_devices_audio_input_label}")
        lines.append(f"media_device_0_device_id={audio_in_did}")
        lines.append(f"media_device_0_group_id={audio_grp_id}")
        lines.append("media_device_1_kind=audiooutput")
        lines.append(f"media_device_1_label={self.media_devices_audio_output_label}")
        lines.append(f"media_device_1_device_id={audio_out_did}")
        lines.append(f"media_device_1_group_id={audio_grp_id}")
        lines.append("media_device_2_kind=videoinput")
        lines.append(f"media_device_2_label={self.media_devices_video_input_label}")
        lines.append(f"media_device_2_device_id={video_did}")
        lines.append(f"media_device_2_group_id={video_grp_id}")
        lines.append("")

        # Battery
        lines.append("# Battery")
        lines.append(f"battery_charging={'true' if self.battery_charging else 'false'}")
        lines.append(f"battery_level={self.battery_level}")
        lines.append(f"battery_charging_time={self.battery_charging_time}")
        lines.append(f"battery_discharging_time={'inf' if math.isinf(self.battery_discharging_time) else str(int(self.battery_discharging_time))}")
        lines.append("")

        # Connection
        lines.append("# Connection")
        lines.append(f"connection_downlink={self.connection_downlink}")
        lines.append(f"connection_effective_type={self.connection_effective_type}")
        lines.append(f"connection_rtt={self.connection_rtt}")
        lines.append(f"connection_save_data={'true' if self.connection_save_data else 'false'}")
        lines.append("")

        # Extra
        lines.append("# Extra")
        lines.append(f"do_not_track={'true' if self.do_not_track else 'false'}")
        lines.append(f"block_port_scan={'1' if self.block_port_scan else '0'}")
        lines.append(f"history_length_min={self.history_length_min}")
        lines.append("")

        # CDP Stealth (always enabled)
        lines.append("# CDP Stealth")
        cdp_mode = self.cdp_mode if self.cdp_mode in ("paranoid", "isolated") else "paranoid"
        lines.append(f"cdp_mode={cdp_mode}")
        lines.append("cdp_stealth=1")
        lines.append("cdp_hide_json_endpoint=1")
        lines.append("cdp_filter_stack_traces=1")
        lines.append("cdp_suppress_console_replay=1")
        lines.append("cdp_suppress_script_enum=1")
        lines.append("cdp_normalize_timing=1")
        lines.append("cdp_fix_screen_coords=1")
        lines.append("")

        # Screen extras
        lines.append("# Screen extras")
        lines.append("screen_avail_left=0")
        lines.append("screen_avail_top=0")
        lines.append(f"pixel_depth={self.color_depth}")
        lines.append("")

        # WebGPU flag
        lines.append("# WebGPU")
        lines.append("webgpu_enabled=1")
        lines.append("")

        # WebRTC blocking
        lines.append("# WebRTC")
        lines.append("webrtc_block=1")
        lines.append("")

        return '\n'.join(lines)

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
        data["canvas_noise_enabled"] = True
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
        gpu_vendor_preference: Optional[str] = None
    ) -> FingerprintProfile:
        """
        Generate unique fingerprint profile.

        Args:
            platform: "Win32", "MacIntel", or "Linux x86_64"
            gpu_vendor_preference: "nvidia", "amd", "intel", or None

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
