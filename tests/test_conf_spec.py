"""Unit tests for the canonical .conf serializer (huligan.conf_spec)."""

from huligan.conf_spec import render_conf, media_device_ids, default_media_devices


def _kv(text):
    d = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        d[k.strip()] = v.strip()
    return d


def test_none_and_absent_keys_are_omitted():
    out = _kv(render_conf({"screen_width": 1920, "webgl_vendor": None}))
    assert out["screen_width"] == "1920"
    assert "webgl_vendor" not in out          # None -> omitted
    assert "webgl_renderer" not in out        # absent -> omitted


def test_correct_key_name_for_client_rects():
    out = _kv(render_conf({"client_rects_noise_seed": 42}))
    assert out["client_rects_noise_seed"] == "42"
    assert "client_rects_seed" not in out     # the GUI's old wrong name must never appear


def test_value_formats():
    out = _kv(render_conf({
        "device_pixel_ratio": 1.0,
        "battery_charging": True,
        "connection_save_data": False,
        "webrtc_block": True,          # flag -> 1/0
        "block_port_scan": True,
        "battery_discharging_time": float("inf"),
        "fonts": ["Arial", "Verdana"],
        "preferred_color_scheme": "dark",
    }))
    assert out["device_pixel_ratio"] == "1.0"
    assert out["battery_charging"] == "true"
    assert out["connection_save_data"] == "false"
    assert out["webrtc_block"] == "1"
    assert out["block_port_scan"] == "1"
    assert out["battery_discharging_time"] == "inf"
    assert out["fonts"] == "Arial,Verdana"
    assert out["preferred_color_scheme"] == "dark"


def test_battery_discharging_time_finite():
    out = _kv(render_conf({"battery_discharging_time": 3600.0}))
    assert out["battery_discharging_time"] == "3600"


def test_audio_noise_seed_always_zero():
    # Even a non-zero input is forced to 0 (BrowserScan flags non-zero as tampering).
    out = _kv(render_conf({"audio_noise_seed": 999}))
    assert out["audio_noise_seed"] == "0"


def test_media_devices_block():
    devs = default_media_devices(
        12345, audio_in_label="Mic", audio_out_label="Spk", video_label="Cam"
    )
    out = _kv(render_conf({"media_devices": devs}))
    assert out["media_devices_count"] == "3"
    assert out["media_device_0_kind"] == "audioinput"
    assert out["media_device_0_label"] == "Mic"
    assert out["media_device_2_kind"] == "videoinput"
    # device/group IDs are the SHA-derived values
    ids = media_device_ids(12345)
    assert out["media_device_0_device_id"] == ids["audio_in_device"]
    assert out["media_device_0_group_id"] == ids["audio_group"]
    assert out["media_device_1_group_id"] == ids["audio_group"]   # speakers share the audio group
    assert out["media_device_2_group_id"] == ids["video_group"]


def test_media_device_ids_deterministic():
    assert media_device_ids(7) == media_device_ids(7)
    assert media_device_ids(7) != media_device_ids(8)


def test_webgl_params_sorted_and_lists_joined():
    out = _kv(render_conf({"webgl_params": {3386: [16384, 16384], 3379: 16384}}))
    assert out["webgl_param_3379"] == "16384"
    assert out["webgl_param_3386"] == "16384,16384"


def test_empty_render_is_safe():
    assert render_conf({}).strip() == ""
