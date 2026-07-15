"""Tests for the public integration primitives (T1.3):
``ensure_binary`` and ``get_default_stealth_args``.
"""
import huligan
from huligan import ensure_binary, get_default_stealth_args
from huligan.launch_plan import _STEALTH_DISABLE_FEATURES, build_launch_plan


def test_exports_present():
    assert hasattr(huligan, "ensure_binary")
    assert hasattr(huligan, "get_default_stealth_args")
    assert "ensure_binary" in huligan.__all__
    assert "get_default_stealth_args" in huligan.__all__


def test_ensure_binary_delegates_to_ensure_chrome():
    # ensure_binary must forward to ensure_chrome (guarantees the *patched* build),
    # NOT to find_chrome (which can fall through to a system PATH chrome).
    assert ensure_binary is huligan.ensure_binary
    assert ensure_binary is not huligan.find_chrome
    assert ensure_binary.__module__ == "huligan.installer"


def test_get_default_stealth_args_exact():
    assert get_default_stealth_args() == [
        "--no-sandbox",
        "--disable-features=TLSTrustAnchorIDs,TlsMldsaSignatures",
    ]


def test_stealth_args_do_not_drift_from_launch_plan():
    """The public stealth flags must match what build_launch_plan actually emits;
    both derive from _STEALTH_DISABLE_FEATURES, so this locks them together and
    a future Chrome upgrade can't change one without the other."""
    argv, _env = build_launch_plan(
        chrome_path="chrome.exe",
        profile_path="x.conf",
        cdp_port=9222,
        user_data_dir="ud",
    )
    plan_df = [a for a in argv if a.startswith("--disable-features=")]
    assert len(plan_df) == 1, "build_launch_plan must emit exactly one --disable-features"
    plan_features = set(plan_df[0].split("=", 1)[1].split(","))

    stealth = get_default_stealth_args()
    stealth_df = [a for a in stealth if a.startswith("--disable-features=")][0]
    stealth_features = set(stealth_df.split("=", 1)[1].split(","))

    assert stealth_features == plan_features == set(_STEALTH_DISABLE_FEATURES)
    assert "--no-sandbox" in argv and "--no-sandbox" in stealth
