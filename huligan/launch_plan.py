"""Shared, pure launch-plan construction for the Huligan browser.

This is the single source of truth for the Chrome command line + environment
that makes Huligan an *antidetect* browser on the proxy path: the SOCKS5
forwarder hand-off, the WebRTC/DNS leak flags, the ``host-resolver-rules``
exclusion, the GeoIP language flags, and the ``HULIGAN_CONFIG_PATH`` /
``HULIGAN_CDP_MODE`` env wiring.

Both entry points consume it so they can never drift:
  - the async automation :class:`huligan.browser.Browser`
  - the sync, persistent :func:`huligan.persistent.launch_persistent`

``build_launch_plan`` is intentionally **pure and synchronous**: it takes
already-resolved inputs (the forwarder port after ``await forwarder.start()``,
the parsed ``proxy_info``, the GeoIP-resolved language/timezone, the
``cdp_mode`` read from the .conf) and returns ``(argv, env)``. It performs no
network I/O, no ``await``, and never starts a forwarder — that keeps it trivial
both to unit-test and to call from synchronous Qt code.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Optional, Tuple, Union


# Always-on, runtime-independent stealth features (build_launch_plan annotates
# WHY these two TLS features are pinned OFF, at the use site below). Shared with
# get_default_stealth_args() so the command-line pins and the public integration
# primitive have exactly ONE definition and can never drift on a Chrome upgrade.
_STEALTH_DISABLE_FEATURES = ("TLSTrustAnchorIDs", "TlsMldsaSignatures")


def build_launch_plan(
    *,
    chrome_path: Union[str, Path],
    profile_path: Union[str, Path],
    cdp_port: int,
    user_data_dir: Union[str, Path],
    forwarder_port: Optional[int] = None,
    proxy_info: Optional[dict] = None,
    webrtc_spoof_ip: Optional[str] = None,
    language: Optional[str] = None,
    timezone: Optional[str] = None,
    cdp_mode: Optional[str] = None,
    headless: bool = False,
    extra_args: Optional[list] = None,
    url: Optional[str] = None,
    base_env: Optional[dict] = None,
) -> Tuple[list, dict]:
    """Build the Chrome ``argv`` list and process ``env`` dict.

    Args:
        chrome_path: Path to chrome(.exe).
        profile_path: Absolute path to the .conf — wired into
            ``HULIGAN_CONFIG_PATH`` so the patched binary reads the fingerprint.
        cdp_port: Remote debugging port.
        user_data_dir: Chrome ``--user-data-dir`` (already resolved by caller).
        forwarder_port: Local port of a running :class:`ProxyForwarder`. When
            set, Chrome is pointed at ``socks5://127.0.0.1:<forwarder_port>``
            (no-auth) and the forwarder bridges to the authenticated upstream.
            Takes precedence over a direct ``proxy_info`` proxy-server.
        proxy_info: Parsed proxy dict (``host``/``port``/``type``). Used for the
            direct ``--proxy-server`` (when there is no forwarder) and always for
            the leak-prevention ``host-resolver-rules`` / WebRTC flags.
        webrtc_spoof_ip: When truthy, the patched binary rewrites WebRTC ICE
            candidate IPs at the source, so the blanket
            ``disable_non_proxied_udp`` flag is omitted. When falsy (and a proxy
            is set) the blanket flag is added to avoid a real-IP leak.
        language: Resolved Accept-Language string (e.g. ``"fi-FI,fi,en-US,en"``).
        timezone: IANA timezone; exported as ``TZ`` when set.
        cdp_mode: ``"paranoid"`` | ``"isolated"`` (from the .conf). Exported as
            ``HULIGAN_CDP_MODE`` unless already present in ``base_env``.
        headless: Append ``--headless=new``.
        extra_args: Additional Chrome flags appended verbatim.
        url: Optional positional start URL (persistent GUI launch). The async
            ``Browser`` passes ``None`` (it opens pages via CDP).
        base_env: Base environment to copy (defaults to ``os.environ``).

    Returns:
        ``(argv, env)`` ready for ``subprocess.Popen``.
    """
    args = [str(chrome_path), "--no-sandbox"]

    # CDP
    args.append(f"--remote-debugging-port={cdp_port}")
    args.append("--remote-allow-origins=*")

    # Proxy: a running local forwarder (no-auth SOCKS5) takes precedence over a
    # direct proxy-server, because Chrome cannot do SOCKS5 auth natively.
    if forwarder_port is not None:
        args.append(f"--proxy-server=socks5://127.0.0.1:{forwarder_port}")
    elif proxy_info:
        args.append(
            f"--proxy-server={proxy_info['type']}://"
            f"{proxy_info['host']}:{proxy_info['port']}"
        )

    # Proxy leak prevention (applies whether forwarder or direct).
    if proxy_info:
        # EXCLUDE the proxy IP so Chrome reaches the proxy server directly.
        # For HTTP proxies this is critical — Chrome sends CONNECT to the proxy IP.
        proxy_ip = proxy_info["host"]
        args.append(
            f"--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1 , EXCLUDE {proxy_ip}"
        )
        # With a spoof IP wired into the .conf, let the patched binary gather
        # candidates and rewrite their IP at the source (port.cc). Without one,
        # fall back to the blanket-disable flag — disabled WebRTC is its own
        # signal (<1% of real users) but still better than leaking the real IP.
        if not webrtc_spoof_ip:
            args.append("--force-webrtc-ip-handling-policy=disable_non_proxied_udp")
        args.append("--enforce-webrtc-ip-permission-check")

    # Features to disable, emitted as a SINGLE --disable-features switch.
    # Chrome keeps only the last --disable-features on the command line, so we
    # must collect everything here and join once — never append the switch twice.
    # These two TLS features are gradual-rollout / Finch-flippable and live in
    # _STEALTH_DISABLE_FEATURES (module top): kTLSTrustAnchorIDs adds ClientHello
    # ext 0xCA34 (JA4 t13d1517h2 -> t13d1518h2, a non-Chrome TLS fingerprint WAFs
    # like SafeLine flag); kTlsMldsaSignatures adds ML-DSA codepoints to
    # signature_algorithms. Pinned OFF so JA4 always matches stock Chrome
    # (t13d1517h2_8daaf6152771_b6f405a00624, measured against 149 patched / 150
    # stock). The Finch seed toggling them is what made detection intermittent.
    disable_features = list(_STEALTH_DISABLE_FEATURES)

    # Language from GeoIP
    if language:
        primary_lang = language.split(",")[0].split("-")[0]
        args.append(f"--lang={primary_lang}")
        args.append(f"--accept-lang={language}")
        # Prevent Chrome from reducing navigator.languages / Accept-Language to one entry.
        disable_features.extend(["ReduceAcceptLanguage", "ReduceAcceptLanguageHTTP"])
        args.append("--disable-reduce-accept-language")

    args.append("--disable-features=" + ",".join(disable_features))

    # User data dir
    args.append(f"--user-data-dir={user_data_dir}")

    # Headless
    if headless:
        args.append("--headless=new")

    # Extra args
    if extra_args:
        args.extend(extra_args)

    # Optional positional start URL (persistent/GUI launch only).
    if url:
        args.append(url)

    # Environment
    env = (base_env if base_env is not None else os.environ).copy()
    env["HULIGAN_CONFIG_PATH"] = str(profile_path)
    if timezone:
        env["TZ"] = timezone
    if cdp_mode and not env.get("HULIGAN_CDP_MODE"):
        env["HULIGAN_CDP_MODE"] = cdp_mode

    return args, env


def get_default_stealth_args() -> list:
    """Canonical always-on stealth flags for launching the patched binary under
    an external driver (Selenium / undetected-chromedriver / any tool that takes
    ``binary_location`` + args).

    Returns exactly the runtime-INDEPENDENT subset::

        --no-sandbox
        --disable-features=TLSTrustAnchorIDs,TlsMldsaSignatures

    Deliberately EXCLUDED (they need runtime values you supply yourself):
      * proxy / host-resolver / WebRTC leak flags (need the proxy + spoof IP)
      * --lang / --accept-lang                    (need the resolved Accept-Language)
      * --remote-debugging-port / --user-data-dir (owned by the driver)
      * --headless=new

    Want those wired for free? Don't launch Chrome yourself - launch via
    :func:`huligan.launch_persistent` and hand its ``.cdp_url`` to your tool.

    WARNING: Chrome keeps only the LAST ``--disable-features`` switch. If you add
    your own, MERGE these feature names into it, or you silently drop the JA4 pins.
    """
    return ["--no-sandbox", "--disable-features=" + ",".join(_STEALTH_DISABLE_FEATURES)]


def cdp_mode_from_conf(profile_path: Union[str, Path, None]) -> Optional[str]:
    """Read ``cdp_mode`` from a .conf file.

    Returns ``"paranoid"`` or ``"isolated"`` if a valid value is found, else
    ``None`` (the caller then keeps any env-var the operator already set).

    Cheap line scan — .conf files are short and the key sits near the bottom.
    We deliberately avoid parsing the whole file to keep this hot-path
    dependency-free.
    """
    if not profile_path:
        return None
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "cdp_mode":
                    value = value.strip().lower()
                    if value in ("paranoid", "isolated"):
                        return value
                    return None
    except OSError:
        return None
    return None


def read_conf_value(profile_path: Union[str, Path, None], key: str) -> Optional[str]:
    """Return the raw string value of a single ``key`` in a .conf, else ``None``.

    First match wins; comments and blank lines are skipped. Used to honour a
    .conf-supplied ``webrtc_local_ipv4`` over an auto-detected one.
    """
    if not profile_path:
        return None
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip()
    except OSError:
        return None
    return None


def find_free_port() -> int:
    """Bind to port 0 on loopback and return the OS-assigned free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def update_conf_keys(profile_path: Union[str, Path, None], updates: dict) -> None:
    """Set/replace ``key=value`` lines in a .conf, appending any missing keys.

    Read-modify-write that preserves comments, blank lines, and the order of
    untouched keys. Values must already be stringified by the caller. No-op when
    ``profile_path`` is falsy or ``updates`` is empty.

    This is the one place the .conf line-rewrite lives; both
    :meth:`Browser._update_conf` and the persistent launcher reuse it instead of
    duplicating the loop.
    """
    if not profile_path or not updates:
        return

    with open(profile_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(profile_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
