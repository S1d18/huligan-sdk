"""Canonical `.conf` serializer — the single source of truth for the contract.

The ``.conf`` file is THE interface between the SDK and the patched Chromium
binary (read via ``HULIGAN_CONFIG_PATH`` / ``profile_reader.h``). Key names,
value formats, and the media-device-ID derivation live here ONCE so that every
producer — the SDK's :class:`FingerprintProfile` and the desktop app's GUI
``Profile`` — emits an identical, complete, contract-correct file and can never
drift.

Design:
- :func:`render_conf` takes a flat ``dict`` of ``conf_key -> python value`` and
  emits the file in canonical sections. **A value of ``None`` (or an absent key)
  omits that line** — this is how a producer keeps "real value passthrough"
  (e.g. not writing ``webgl_vendor`` so the real GPU shows, exactly as the
  reference profile does). Callers decide *which* keys to spoof; this module
  decides *how* every key is named and formatted.
- Composite inputs: ``webgl_params`` (``{gl_enum: value}``) and ``media_devices``
  (list of ``{kind,label,device_id,group_id}``).
- Key names verified against huligan-browser ``docs/PARAMETER_MAPPING.md`` and
  ``patches/profiles/dolphin_anty_reference.conf`` (2026-06-05). Notably the
  binary reads ``client_rects_noise_seed`` (NOT ``client_rects_seed``).
"""

from __future__ import annotations

import hashlib
import math
from typing import Optional


# --- value formatters (return None to omit the line) ----------------------

def _s(x):
    return None if x is None else str(x)


def _i(x):
    return None if x is None else str(int(x))


def _f(x):
    return None if x is None else str(float(x))


def _tf(x):
    """Boolean as true/false (most API-value bools)."""
    return None if x is None else ("true" if x else "false")


def _flag(x):
    """Boolean as 1/0 (legacy C++ gate flags: cdp_*, webgpu_enabled, …)."""
    return None if x is None else ("1" if x else "0")


def _csv(xs):
    if not xs:
        return None
    return ",".join(str(i) for i in xs)


def _dischg(x):
    if x is None:
        return None
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return str(int(x))


def media_device_ids(canvas_noise_seed) -> dict:
    """Derive stable, per-profile media-device IDs from the canvas seed.

    The patched binary expects SHA-256-derived deviceId/groupId tied to the
    profile seed (see ``patches/profiles/dolphin_anty_reference.conf``). Shared
    so the SDK and the GUI derive identical IDs for the same seed.
    """
    s = str(canvas_noise_seed)

    def mid(suffix: str) -> str:
        return hashlib.sha256(f"{s}_{suffix}".encode()).hexdigest()

    return {
        "audio_in_device": mid("audio_in_device"),
        "audio_group": mid("audio_group"),
        "audio_out_device": mid("audio_out_device"),
        "video_device": mid("video_device"),
        "video_group": mid("video_group"),
    }


def default_media_devices(canvas_noise_seed, *, audio_in_label, audio_out_label, video_label) -> list:
    """Build the standard 3-device list (mic + speakers + webcam) with derived IDs."""
    ids = media_device_ids(canvas_noise_seed)
    return [
        {"kind": "audioinput", "label": audio_in_label,
         "device_id": ids["audio_in_device"], "group_id": ids["audio_group"]},
        {"kind": "audiooutput", "label": audio_out_label,
         "device_id": ids["audio_out_device"], "group_id": ids["audio_group"]},
        {"kind": "videoinput", "label": video_label,
         "device_id": ids["video_device"], "group_id": ids["video_group"]},
    ]


def render_conf(v: dict, *, header: Optional[str] = None) -> str:
    """Render a canonical ``.conf`` from a value dict (``None`` => omit the key).

    Recognised composite keys in ``v``:
      - ``webgl_params``: ``{gl_enum: value}`` (value may be a list).
      - ``media_devices``: ``[{kind,label,device_id,group_id}, ...]``.

    Returns the file contents as a string (no trailing newline normalisation
    beyond a single terminating newline).
    """
    out: list = []
    g = v.get

    def section(comment: str, pairs):
        seg = [f"{k}={s}" for k, s in pairs if s is not None]
        if seg:
            out.append(f"# {comment}")
            out.extend(seg)
            out.append("")

    if header:
        out.append(f"# {header}")
        out.append("")

    # Screen
    section("Screen", [
        ("screen_width", _i(g("screen_width"))),
        ("screen_height", _i(g("screen_height"))),
        ("screen_avail_width", _i(g("screen_avail_width"))),
        ("screen_avail_height", _i(g("screen_avail_height"))),
        ("outer_width", _i(g("outer_width"))),
        ("outer_height", _i(g("outer_height"))),
        ("color_depth", _i(g("color_depth"))),
        ("device_pixel_ratio", _f(g("device_pixel_ratio"))),
    ])

    # Hardware
    section("Hardware", [
        ("cpu_cores", _i(g("cpu_cores"))),
        ("device_memory", _i(g("device_memory"))),
        ("platform", _s(g("platform"))),
        ("max_touch_points", _i(g("max_touch_points"))),
    ])

    # WebGL (vendor/renderer omitted => real GPU passthrough, as the reference does)
    webgl_pairs = [
        ("webgl_vendor", _s(g("webgl_vendor"))),
        ("webgl_renderer", _s(g("webgl_renderer"))),
        ("webgl_extensions", _csv(g("webgl_extensions"))),
        ("webgl2_extensions", _csv(g("webgl2_extensions"))),
    ]
    params = g("webgl_params") or {}
    for gl_enum, value in sorted(params.items()):
        if isinstance(value, (list, tuple)):
            webgl_pairs.append((f"webgl_param_{gl_enum}", ",".join(str(x) for x in value)))
        else:
            webgl_pairs.append((f"webgl_param_{gl_enum}", str(value)))
    section("WebGL", webgl_pairs)

    # WebGPU descriptor (+ optional v2 limits/features)
    section("WebGPU", [
        ("webgpu_vendor", _s(g("webgpu_vendor"))),
        ("webgpu_architecture", _s(g("webgpu_architecture"))),
        ("webgpu_device", _s(g("webgpu_device"))),
        ("webgpu_description", _s(g("webgpu_description"))),
        ("webgpu_max_buffer_size", _i(g("webgpu_max_buffer_size")) if g("webgpu_max_buffer_size") else None),
        ("webgpu_max_storage_buffer_binding_size",
         _i(g("webgpu_max_storage_buffer_binding_size")) if g("webgpu_max_storage_buffer_binding_size") else None),
        ("webgpu_max_compute_workgroup_size_x",
         _i(g("webgpu_max_compute_workgroup_size_x")) if g("webgpu_max_compute_workgroup_size_x") else None),
        ("webgpu_max_compute_workgroup_size_y",
         _i(g("webgpu_max_compute_workgroup_size_y")) if g("webgpu_max_compute_workgroup_size_y") else None),
        ("webgpu_max_compute_workgroup_size_z",
         _i(g("webgpu_max_compute_workgroup_size_z")) if g("webgpu_max_compute_workgroup_size_z") else None),
        ("webgpu_features", _csv(g("webgpu_features"))),
        ("webgpu_subgroup_min_size", _i(g("webgpu_subgroup_min_size")) if g("webgpu_subgroup_min_size") else None),
        ("webgpu_subgroup_max_size", _i(g("webgpu_subgroup_max_size")) if g("webgpu_subgroup_max_size") else None),
    ])

    # Noise seeds
    section("Noise Seeds", [
        ("canvas_noise_seed", _i(g("canvas_noise_seed"))),
        ("canvas_noise_enabled", _tf(g("canvas_noise_enabled"))),
        # Audio buffer noise is disabled (BrowserScan flags non-zero as tampering).
        ("audio_noise_seed", "0" if g("audio_noise_seed") is not None else None),
        ("font_noise_seed", _i(g("font_noise_seed"))),
        ("client_rects_noise_seed", _i(g("client_rects_noise_seed"))),
    ])

    # Audio properties (read by patch 09_audio — were missing from the SDK)
    section("Audio", [
        ("audio_sample_rate", _i(g("audio_sample_rate"))),
        ("audio_max_channel_count", _i(g("audio_max_channel_count"))),
        ("audio_base_latency", _f(g("audio_base_latency"))),
        ("audio_output_latency", _f(g("audio_output_latency"))),
    ])

    # Fonts
    section("Fonts", [
        ("fonts", _csv(g("fonts"))),
        ("fonts_dir", _s(g("fonts_dir")) if g("fonts_dir") else None),
    ])

    # Geolocation / locale
    section("Geolocation", [
        ("languages", _s(g("languages"))),
        ("intl_locale", _s(g("intl_locale")) if g("intl_locale") else None),
        ("geolocation_latitude", _f(g("geolocation_latitude"))),
        ("geolocation_longitude", _f(g("geolocation_longitude"))),
        ("geolocation_accuracy", _i(g("geolocation_accuracy"))),
        ("timezone", _s(g("timezone"))),
    ])

    # Media devices
    devices = g("media_devices") or []
    if devices:
        media_pairs = [("media_devices_count", str(len(devices)))]
        for idx, d in enumerate(devices):
            media_pairs.append((f"media_device_{idx}_kind", _s(d.get("kind"))))
            media_pairs.append((f"media_device_{idx}_label", _s(d.get("label"))))
            media_pairs.append((f"media_device_{idx}_device_id", _s(d.get("device_id"))))
            media_pairs.append((f"media_device_{idx}_group_id", _s(d.get("group_id"))))
        section("Media Devices", media_pairs)

    # Battery
    section("Battery", [
        ("battery_enabled", _tf(g("battery_enabled"))),
        ("battery_charging", _tf(g("battery_charging"))),
        ("battery_level", _f(g("battery_level"))),
        ("battery_charging_time", _i(g("battery_charging_time"))),
        ("battery_discharging_time", _dischg(g("battery_discharging_time"))),
    ])

    # Connection
    section("Connection", [
        ("connection_type", _s(g("connection_type"))),
        ("connection_downlink", _f(g("connection_downlink"))),
        ("connection_effective_type", _s(g("connection_effective_type"))),
        ("connection_rtt", _i(g("connection_rtt"))),
        ("connection_save_data", _tf(g("connection_save_data"))),
    ])

    # Extra
    section("Extra", [
        ("do_not_track", _tf(g("do_not_track"))),
        ("block_port_scan", _flag(g("block_port_scan"))),
        ("history_length_min", _i(g("history_length_min"))),
        # default dark — avoids the CreepJS "prefersLightColor: true" headless tell
        ("preferred_color_scheme", _s(g("preferred_color_scheme"))),
    ])

    # CDP stealth
    section("CDP Stealth", [
        ("cdp_mode", _s(g("cdp_mode"))),
        ("cdp_stealth", _flag(g("cdp_stealth"))),
        ("cdp_hide_json_endpoint", _flag(g("cdp_hide_json_endpoint"))),
        ("cdp_filter_stack_traces", _flag(g("cdp_filter_stack_traces"))),
        ("cdp_suppress_console_replay", _flag(g("cdp_suppress_console_replay"))),
        ("cdp_suppress_script_enum", _flag(g("cdp_suppress_script_enum"))),
        ("cdp_normalize_timing", _flag(g("cdp_normalize_timing"))),
        ("cdp_fix_screen_coords", _flag(g("cdp_fix_screen_coords"))),
    ])

    # Screen extras
    section("Screen extras", [
        ("screen_avail_left", _i(g("screen_avail_left"))),
        ("screen_avail_top", _i(g("screen_avail_top"))),
        ("pixel_depth", _i(g("pixel_depth"))),
    ])

    # WebGPU availability flag
    section("WebGPU flag", [
        ("webgpu_enabled", _flag(g("webgpu_enabled"))),
    ])

    # WebRTC
    section("WebRTC", [
        ("webrtc_block", _flag(g("webrtc_block"))),
        ("webrtc_local_ipv4", _s(g("webrtc_local_ipv4")) if g("webrtc_local_ipv4") else None),
        ("webrtc_local_ipv6", _s(g("webrtc_local_ipv6")) if g("webrtc_local_ipv6") else None),
        ("webrtc_public_ipv4", _s(g("webrtc_public_ipv4")) if g("webrtc_public_ipv4") else None),
        ("webrtc_private_ipv4", _s(g("webrtc_private_ipv4")) if g("webrtc_private_ipv4") else None),
        ("webrtc_public_ipv6", _s(g("webrtc_public_ipv6")) if g("webrtc_public_ipv6") else None),
        ("webrtc_private_ipv6", _s(g("webrtc_private_ipv6")) if g("webrtc_private_ipv6") else None),
    ])

    return "\n".join(out).rstrip("\n") + "\n"
