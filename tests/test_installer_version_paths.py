"""VER-PATH-01: a version string is used as a path under the Chrome cache.

Before the fix ``remove_version('')`` deleted the cache root itself and
``remove_version('..')`` its PARENT; ``ensure_chrome`` / ``chrome pin`` accepted
any string. Every entry point must now reject anything that is not a dotted
four-part numeric version before touching the filesystem, and every derived path
must stay inside the cache root.
"""

import pytest

from huligan import __main__ as cli
from huligan import installer

BAD_VERSIONS = [
    "",
    ".",
    "..",
    "../x",
    "..\\x",
    "152.0.7977.65/../..",
    "152.0.7977",
    "152.0.7977.65.1",
    "152.0.7977.65 ",
    "v152.0.7977.65",
    "C:\\Windows",
    "/etc",
    "152.0.7977.6a",
    "152.0.7977.65\n",
]


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    root = tmp_path / "cache" / "chrome"
    root.mkdir(parents=True)
    monkeypatch.setenv("HULIGAN_CHROME_DIR", str(root))
    monkeypatch.delenv("HULIGAN_CHROME_CHANNEL", raising=False)
    monkeypatch.delenv("HULIGAN_GH_TOKEN", raising=False)
    return root


def _sentinels(cache_dir):
    # A canary next to the cache root and one inside it: neither may vanish.
    outside = cache_dir.parent / "canary.txt"
    outside.write_text("outside")
    inside = cache_dir / "manifest.json"
    inside.write_text("{}")
    return outside, inside


@pytest.mark.parametrize("bad", BAD_VERSIONS)
def test_remove_version_rejects_bad_version_and_deletes_nothing(cache_dir, bad):
    outside, inside = _sentinels(cache_dir)
    with pytest.raises(ValueError):
        installer.remove_version(bad)
    assert cache_dir.is_dir()
    assert outside.read_text() == "outside"
    assert inside.read_text() == "{}"


@pytest.mark.parametrize("bad", ["", "..", "../x", "1.2.3"])
def test_ensure_chrome_rejects_bad_version_before_any_io(cache_dir, monkeypatch, bad):
    def no_io(*a, **k):
        raise AssertionError("must not reach network / download")
    monkeypatch.setattr(installer, "_download", no_io)
    monkeypatch.setattr(installer.urllib.request, "urlopen", no_io)
    monkeypatch.setattr(installer.sys, "platform", "win32")
    with pytest.raises(ValueError):
        installer.ensure_chrome(bad)


def test_manifest_supplied_bad_version_is_rejected(cache_dir, monkeypatch):
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: {"latest": "..", "versions": {}})
    with pytest.raises(ValueError):
        installer.resolve_version("latest")


def test_bad_config_pin_is_rejected(cache_dir):
    installer._save_config({"channel": "pinned", "pinned_version": ".."})
    with pytest.raises(ValueError):
        installer.resolve_launch_target()


@pytest.mark.parametrize("bad", ["", "..", "../x"])
def test_is_installed_bad_version_is_false(cache_dir, bad):
    (cache_dir / "chrome.exe").write_text("x")
    (cache_dir / ".ok").write_text("x")
    assert installer.is_installed(bad) is False


def test_valid_version_still_removed(cache_dir):
    v = "152.0.7977.65"
    (cache_dir / v).mkdir()
    (cache_dir / v / "chrome.exe").write_text("x")
    (cache_dir / f"{v}.ok").write_text(v)
    assert installer.remove_version(v) is True
    assert not (cache_dir / v).exists()
    assert cache_dir.is_dir()


@pytest.mark.parametrize("bad", ["..", "../x", "latest", "1.2.3"])
def test_cli_pin_rejects_bad_version(cache_dir, capsys, bad):
    assert cli.main(["chrome", "pin", bad]) != 0
    assert "pinned_version" not in installer._load_config()
