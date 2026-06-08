"""Golden regression for FingerprintProfile.to_conf after the conf_spec migration.

seed=1 is deterministic. The pre-migration output (captured 2026-06-05) had 86
keys; the migration must preserve every one of them with the same value, and add the
previously-missing keys (audio properties + preferred_color_scheme, plus
battery_enabled + connection_type for SDK<->GUI .conf parity).
This guards the live-validated launch path (validate_launch.py PASS on a US proxy).
"""

from huligan import FingerprintGenerator
from huligan.conf_spec import media_device_ids


def _kv(text):
    d = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        d[k.strip()] = v.strip()
    return d


# The exact 86 keys the pre-consolidation serializer emitted for seed=1.
GOLDEN_86 = {
    "audio_noise_seed", "battery_charging", "battery_charging_time",
    "battery_discharging_time", "battery_level", "block_port_scan",
    "canvas_noise_enabled", "canvas_noise_seed", "cdp_filter_stack_traces",
    "cdp_fix_screen_coords", "cdp_hide_json_endpoint", "cdp_mode",
    "cdp_normalize_timing", "cdp_stealth", "cdp_suppress_console_replay",
    "cdp_suppress_script_enum", "client_rects_noise_seed", "color_depth",
    "connection_downlink", "connection_effective_type", "connection_rtt",
    "connection_save_data", "cpu_cores", "device_memory", "device_pixel_ratio",
    "do_not_track", "font_noise_seed", "fonts", "geolocation_accuracy",
    "geolocation_latitude", "geolocation_longitude", "history_length_min",
    "languages", "max_touch_points",
    "media_device_0_device_id", "media_device_0_group_id", "media_device_0_kind",
    "media_device_0_label", "media_device_1_device_id", "media_device_1_group_id",
    "media_device_1_kind", "media_device_1_label", "media_device_2_device_id",
    "media_device_2_group_id", "media_device_2_kind", "media_device_2_label",
    "media_devices_count", "outer_height", "outer_width", "pixel_depth",
    "platform", "screen_avail_height", "screen_avail_left", "screen_avail_top",
    "screen_avail_width", "screen_height", "screen_width", "timezone",
    "webgl2_extensions", "webgl_extensions",
    "webgl_param_3379", "webgl_param_3386", "webgl_param_33901", "webgl_param_33902",
    "webgl_param_34024", "webgl_param_34076", "webgl_param_34921", "webgl_param_34930",
    "webgl_param_35657", "webgl_param_35658", "webgl_param_35659", "webgl_param_35660",
    "webgl_param_35661", "webgl_param_36347", "webgl_param_36348", "webgl_param_36349",
    "webgl_param_37154", "webgl_param_37157",
    "webgl_renderer", "webgl_vendor", "webgpu_architecture", "webgpu_description",
    "webgpu_device", "webgpu_enabled", "webgpu_vendor", "webrtc_block",
}

NEW_KEYS = {
    "audio_sample_rate", "audio_max_channel_count",
    "audio_base_latency", "audio_output_latency", "preferred_color_scheme",
    # SDK<->GUI parity: the GUI Profile already emits these two; the SDK generator
    # was missing them (the BUG_2026-06-05 .conf-key drift this migration fixes).
    "battery_enabled", "connection_type",
}


def test_seed1_keyset_is_golden_plus_new():
    out = _kv(FingerprintGenerator(seed=1).generate().to_conf())
    keys = set(out)
    missing = GOLDEN_86 - keys
    assert not missing, f"regression: dropped keys {sorted(missing)}"
    extra = keys - GOLDEN_86 - NEW_KEYS
    assert not extra, f"unexpected new keys {sorted(extra)}"
    assert NEW_KEYS <= keys, f"missing intended additions {sorted(NEW_KEYS - keys)}"


def test_seed1_spot_values_and_new_additions():
    out = _kv(FingerprintGenerator(seed=1).generate().to_conf())
    # Stable spot-checks of preserved values.
    assert out["screen_width"] == "1920"
    assert out["cdp_mode"] == "paranoid"
    assert out["audio_noise_seed"] == "0"
    assert out["block_port_scan"] == "1"
    assert out["webgpu_enabled"] == "1"
    assert out["battery_discharging_time"] == "inf"
    assert out["client_rects_noise_seed"].isdigit()
    assert "client_rects_seed" not in out          # the wrong key name must be gone
    # New additions present with sane defaults.
    assert out["audio_sample_rate"] == "44100"
    assert out["audio_max_channel_count"] == "2"
    assert out["audio_base_latency"] == "0.01"
    assert out["audio_output_latency"] == "0.02"
    assert out["preferred_color_scheme"] == "dark"
    # SDK<->GUI parity additions (match the GUI Profile defaults).
    assert out["connection_type"] == "ethernet"
    assert "battery_enabled" in out


def test_media_ids_match_shared_derivation():
    prof = FingerprintGenerator(seed=1).generate()
    out = _kv(prof.to_conf())
    ids = media_device_ids(prof.canvas_noise_seed)
    assert out["media_device_0_device_id"] == ids["audio_in_device"]
    assert out["media_device_2_group_id"] == ids["video_group"]
