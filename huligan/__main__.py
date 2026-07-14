"""``huligan`` command-line interface.

Explicit control over which patched Chrome build a machine uses, for CI, farms,
and manual ops. Thin wrapper over :mod:`huligan.installer` — the CLI holds no
resolution logic of its own.

    huligan chrome list                     what's cached + what the channel offers
    huligan chrome update [--channel latest] [--check]
    huligan chrome pin <version> | --clear  persist an exact build (or clear it)
    huligan chrome prune [--keep N]         delete old cached builds
    huligan version
"""

from __future__ import annotations

import argparse
import sys

from . import installer
from .conf_spec import CONF_SCHEMA_VERSION
from .version import CHROME_VERSION, get_version


def _fmt_size(n) -> str:
    try:
        mb = int(n) / (1024 * 1024)
        return f"{mb:.0f} MB"
    except Exception:
        return "?"


# --- chrome list ----------------------------------------------------------

def _cmd_chrome_list(_args) -> int:
    channel, source = installer.effective_channel()
    print(f"SDK build:        {get_version()}")
    print(f".conf schema:     v{CONF_SCHEMA_VERSION}")
    print(f"Pinned (default): {CHROME_VERSION}")
    print(f"Channel:          {channel} (from {source})")

    cfg = installer._load_config()
    if cfg.get("pinned_version"):
        print(f"Pinned override:  {cfg['pinned_version']}")

    cached = installer.installed_versions()
    print("\nInstalled (cache):")
    if not cached:
        print("  (none - will download on first launch)")
    else:
        for v in cached:
            tag = " <- pinned default" if v == CHROME_VERSION else ""
            print(f"  {v}{tag}")

    manifest = installer._safe_fetch_manifest()
    print("\nManifest:")
    if manifest is None:
        print("  (unreachable - offline or no cache)")
    else:
        print(f"  latest: {manifest.get('latest', '?')}")
        channels = manifest.get("channels") or {}
        for name, ver in channels.items():
            print(f"  {name}: {ver}")
        avail = sorted(manifest.get("versions", {}), key=installer._version_key, reverse=True)
        if avail:
            print(f"  published: {', '.join(avail)}")
    return 0


# --- chrome update --------------------------------------------------------

def _cmd_chrome_update(args) -> int:
    # An explicit --channel both switches the persisted channel and updates.
    if args.channel:
        channel = args.channel.strip().lower()
        if not args.check:
            cfg = installer._load_config()
            cfg["channel"] = channel
            cfg.pop("pinned_version", None)
            installer._save_config(cfg)
            print(f"Channel set to '{channel}'.")
    else:
        channel, _ = installer.effective_channel()

    try:
        version, _sha = installer.resolve_version(channel)
    except installer.IncompatibleBuildError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Could not resolve channel '{channel}': {exc}", file=sys.stderr)
        return 1

    already = installer.is_installed(version)
    if args.check:
        state = "already installed" if already else "NOT installed"
        print(f"Channel '{channel}' -> Chrome {version} ({state}).")
        return 0

    if already:
        print(f"Chrome {version} already installed (channel '{channel}').")
        return 0

    print(f"Updating to Chrome {version} (channel '{channel}')...")
    try:
        path = installer.ensure_chrome(version)
    except Exception as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1
    print(f"Installed at {path}")
    return 0


# --- chrome pin -----------------------------------------------------------

def _cmd_chrome_pin(args) -> int:
    cfg = installer._load_config()

    if args.clear:
        cfg.pop("channel", None)
        cfg.pop("pinned_version", None)
        installer._save_config(cfg)
        print(f"Pin cleared - back to default pinned Chrome {CHROME_VERSION}.")
        return 0

    if not args.version:
        channel, source = installer.effective_channel()
        print(f"Channel: {channel} (from {source})")
        if cfg.get("pinned_version"):
            print(f"Pinned override: {cfg['pinned_version']}")
        else:
            print(f"No exact pin set (default {CHROME_VERSION}).")
        return 0

    cfg["channel"] = "pinned"
    cfg["pinned_version"] = args.version
    installer._save_config(cfg)
    print(f"Pinned to Chrome {args.version}. Run 'huligan chrome update' to fetch it now.")
    return 0


# --- chrome prune ---------------------------------------------------------

def _cmd_chrome_prune(args) -> int:
    keep = max(0, args.keep)
    cached = installer.installed_versions()  # newest first

    # Always protect the pinned default and the currently-resolved launch target.
    protected = {CHROME_VERSION}
    try:
        protected.add(installer.resolve_launch_target()[0])
    except Exception:
        pass

    survivors = list(protected)
    for v in cached:
        if v in protected:
            continue
        if len(survivors) < keep + len(protected):
            survivors.append(v)

    removed = []
    for v in cached:
        if v not in survivors:
            if installer.remove_version(v):
                removed.append(v)

    if not removed:
        print(f"Nothing to prune (keeping {sorted(set(survivors), key=installer._version_key, reverse=True)}).")
    else:
        for v in removed:
            print(f"Removed {v}")
        kept = [v for v in cached if v not in removed]
        print(f"Kept: {', '.join(kept) or '(none)'}")
    return 0


# --- version --------------------------------------------------------------

def _cmd_version(_args) -> int:
    print(get_version())
    print(f"Chrome (pinned): {CHROME_VERSION}")
    print(f".conf schema:    v{CONF_SCHEMA_VERSION}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huligan", description="Huligan Antidetect SDK CLI")
    sub = parser.add_subparsers(dest="group", required=True)

    sub.add_parser("version", help="show SDK / Chrome / schema versions").set_defaults(
        func=_cmd_version)

    chrome = sub.add_parser("chrome", help="manage the patched Chrome build")
    csub = chrome.add_subparsers(dest="cmd", required=True)

    csub.add_parser("list", help="show cached builds + manifest").set_defaults(
        func=_cmd_chrome_list)

    up = csub.add_parser("update", help="download the channel's build")
    up.add_argument("--channel", help="pinned | stable | latest (also persists it)")
    up.add_argument("--check", action="store_true", help="report only, do not download")
    up.set_defaults(func=_cmd_chrome_update)

    pin = csub.add_parser("pin", help="persist an exact build, or show/clear the pin")
    pin.add_argument("version", nargs="?", help="exact version, e.g. 150.0.7871.101")
    pin.add_argument("--clear", action="store_true", help="remove the pin / channel override")
    pin.set_defaults(func=_cmd_chrome_pin)

    pr = csub.add_parser("prune", help="delete old cached builds")
    pr.add_argument("--keep", type=int, default=2,
                    help="keep this many recent builds besides protected ones (default 2)")
    pr.set_defaults(func=_cmd_chrome_prune)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
