"""Public launch-selection API (set_launch_selection / get_launch_selection).

The app used to reach into ``installer._load_config`` / ``_save_config`` to pin
a build. The public setter validates the version, keeps unrelated config keys,
and writes atomically (no half-written config.json survives a failed write).
"""
import json

import pytest

import huligan
from huligan import installer


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HULIGAN_CHROME_DIR", str(tmp_path))
    monkeypatch.delenv("HULIGAN_CHROME_CHANNEL", raising=False)
    return tmp_path


def test_exported_from_package():
    assert huligan.set_launch_selection is installer.set_launch_selection
    assert huligan.get_launch_selection is installer.get_launch_selection
    assert "set_launch_selection" in huligan.__all__


def test_pin_exact_version(cache_dir):
    sel = installer.set_launch_selection(version="152.0.7977.65")
    assert sel == {"channel": "pinned", "pinned_version": "152.0.7977.65"}
    assert installer.resolve_launch_target()[0] == "152.0.7977.65"


def test_channel_clears_pin_and_keeps_other_keys(cache_dir):
    (cache_dir / "config.json").write_text(
        json.dumps({"channel": "pinned", "pinned_version": "1.2.3.4", "extra": 7}))
    sel = installer.set_launch_selection(channel=" Latest ")
    assert sel == {"channel": "latest", "pinned_version": None}
    assert json.loads((cache_dir / "config.json").read_text())["extra"] == 7


def test_clear_back_to_default(cache_dir):
    installer.set_launch_selection(version="152.0.7977.65")
    assert installer.set_launch_selection() == {"channel": None, "pinned_version": None}
    assert installer.effective_channel() == (installer.DEFAULT_CHANNEL, "default")


@pytest.mark.parametrize("bad", ["", "..", "../x", "152.0.7977", "152.0.7977.65/..", 152])
def test_rejects_invalid_version_without_writing(cache_dir, bad):
    with pytest.raises(ValueError):
        installer.set_launch_selection(version=bad)
    assert not (cache_dir / "config.json").exists()


@pytest.mark.parametrize("bad", ["", "../x", "la test", "x" * 40])
def test_rejects_invalid_channel(cache_dir, bad):
    with pytest.raises(ValueError):
        installer.set_launch_selection(channel=bad)


def test_version_with_moving_channel_is_contradiction(cache_dir):
    with pytest.raises(ValueError):
        installer.set_launch_selection(version="152.0.7977.65", channel="latest")


def test_write_is_atomic(cache_dir, monkeypatch):
    installer.set_launch_selection(version="152.0.7977.65")
    before = (cache_dir / "config.json").read_text()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(installer.os, "replace", boom)
    with pytest.raises(OSError):
        installer.set_launch_selection(channel="latest")
    assert (cache_dir / "config.json").read_text() == before
    assert list(cache_dir.glob("config.json.tmp-*")) == []
