"""
Huligan Antidetect - GeoIP Manager

Determines timezone, geolocation, language, and country from an IP address.

Supports:
1. Local MaxMind GeoLite2 database (recommended)
2. Online API fallback (ip-api.com)

Usage:
    from huligan.geoip import GeoIPManager

    manager = GeoIPManager()
    result = manager.lookup("1.2.3.4")
    print(result.timezone, result.language)

    # Or from proxy URL
    result = manager.lookup_proxy("socks5://user:pass@host:port")
"""

import json
import logging
import random
import socket
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any

log = logging.getLogger("huligan.geoip")

# Pre-empt the geoip-hang class of issue: keep per-attempt timeouts
# tight enough that a slow/dead endpoint does not block browser
# launch, and retry a few times with exponential backoff + jitter
# before giving up to defaults.
_ONLINE_PER_ATTEMPT_TIMEOUT = 4.0   # seconds per HTTP attempt
_ONLINE_TOTAL_BUDGET = 12.0          # cap across all attempts
_ONLINE_MAX_ATTEMPTS = 3
_ONLINE_BACKOFF_BASE = 0.6
_ONLINE_BACKOFF_JITTER = 0.4
_DNS_TIMEOUT = 3.0                   # seconds for hostname resolution

# Optional geoip2 import
try:
    import geoip2.database
    import geoip2.errors
    HAS_GEOIP2 = True
except ImportError:
    HAS_GEOIP2 = False

# GeoLite2 database search paths
GEOIP_DB_PATHS = [
    Path(__file__).parent / "data" / "GeoLite2-City.mmdb",
    Path(__file__).parent.parent / "data" / "GeoLite2-City.mmdb",
    Path("/usr/share/GeoIP/GeoLite2-City.mmdb"),
    Path("/var/lib/GeoIP/GeoLite2-City.mmdb"),
    Path("C:/ProgramData/MaxMind/GeoLite2-City.mmdb"),
]

# Country -> language mapping
COUNTRY_LANGUAGE_MAP = {
    "RU": "ru-RU,ru",
    "US": "en-US,en",
    "GB": "en-GB,en",
    "DE": "de-DE,de",
    "FR": "fr-FR,fr",
    "ES": "es-ES,es",
    "IT": "it-IT,it",
    "PT": "pt-PT,pt",
    "BR": "pt-BR,pt",
    "NL": "nl-NL,nl",
    "PL": "pl-PL,pl",
    "UA": "uk-UA,uk",
    "JP": "ja-JP,ja",
    "KR": "ko-KR,ko",
    "CN": "zh-CN,zh",
    "TW": "zh-TW,zh",
    "TR": "tr-TR,tr",
    "AR": "es-AR,es",
    "MX": "es-MX,es",
    "IN": "en-IN,en,hi",
    "AU": "en-AU,en",
    "CA": "en-CA,en,fr",
    "FI": "fi-FI,fi",
    "SE": "sv-SE,sv",
    "NO": "nb-NO,nb,no",
    "DK": "da-DK,da",
    "CZ": "cs-CZ,cs",
    "AT": "de-AT,de",
    "CH": "de-CH,de,fr,it",
    "BE": "nl-BE,nl,fr",
    "IL": "he-IL,he",
    "AE": "ar-AE,ar,en",
    "SA": "ar-SA,ar",
    "EG": "ar-EG,ar",
    "TH": "th-TH,th",
    "VN": "vi-VN,vi",
    "ID": "id-ID,id",
    "MY": "ms-MY,ms,en",
    "SG": "en-SG,en,zh",
    "PH": "en-PH,en,tl",
}

DEFAULT_LANGUAGE = "en-US,en"


class GeoIPResult:
    """GeoIP lookup result."""

    def __init__(self):
        self.ip: str = ""
        self.country_code: str = ""
        self.country_name: str = ""
        self.city: str = ""
        self.region: str = ""
        self.timezone: str = ""
        self.latitude: float = 0.0
        self.longitude: float = 0.0
        self.accuracy: int = 100000  # meters
        self.language: str = DEFAULT_LANGUAGE
        self.source: str = ""  # "local" or "online"
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip": self.ip,
            "country_code": self.country_code,
            "country_name": self.country_name,
            "city": self.city,
            "region": self.region,
            "timezone": self.timezone,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy": self.accuracy,
            "language": self.language,
            "source": self.source,
            "error": self.error,
        }

    def to_conf(self) -> str:
        """Output in .conf format for Huligan."""
        lines = [
            f"# GeoIP data for {self.ip}",
            f"# Source: {self.source}",
            f"# Location: {self.city}, {self.country_name}",
            f"",
            f"timezone={self.timezone}",
            f"geolocation_latitude={self.latitude}",
            f"geolocation_longitude={self.longitude}",
            f"geolocation_accuracy={self.accuracy}",
            f"languages={self.language}",
        ]
        return "\n".join(lines)

    def __str__(self):
        return (
            f"GeoIP({self.ip}): {self.city}, {self.country_name} "
            f"({self.latitude:.4f}, {self.longitude:.4f}) "
            f"TZ={self.timezone} Lang={self.language.split(',')[0]}"
        )


class GeoIPManager:
    """GeoIP manager with local database and online API fallback."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.reader = None
        self._init_database()

    def _init_database(self):
        """Initialize local database."""
        if not HAS_GEOIP2:
            return

        paths_to_try = []
        if self.db_path:
            paths_to_try.append(Path(self.db_path))
        paths_to_try.extend(GEOIP_DB_PATHS)

        for path in paths_to_try:
            if path.exists():
                try:
                    self.reader = geoip2.database.Reader(str(path))
                    return
                except Exception:
                    pass

    def lookup(self, ip: str) -> GeoIPResult:
        """
        Lookup IP address and return geo information.

        Tries local database first, falls back to online API.
        """
        result = GeoIPResult()
        result.ip = ip

        if self.reader:
            try:
                response = self.reader.city(ip)
                result.country_code = response.country.iso_code or ""
                result.country_name = response.country.name or ""
                result.city = response.city.name or ""
                result.region = (
                    response.subdivisions.most_specific.name
                    if response.subdivisions
                    else ""
                )
                result.timezone = response.location.time_zone or ""
                result.latitude = response.location.latitude or 0.0
                result.longitude = response.location.longitude or 0.0
                result.accuracy = response.location.accuracy_radius or 100
                result.accuracy *= 1000  # km -> meters
                result.language = COUNTRY_LANGUAGE_MAP.get(
                    result.country_code, DEFAULT_LANGUAGE
                )
                result.source = "local"
                return result
            except Exception:
                pass

        return self._online_lookup(ip)

    def _online_lookup(self, ip: str) -> GeoIPResult:
        """
        Fallback lookup via ip-api.com with bounded retries.

        Each attempt has a short per-attempt timeout; the loop is
        capped by a total time budget so a sustained outage cannot
        delay browser launch indefinitely. On total failure, returns
        a result with ``error`` set so the caller can decide whether
        to launch without GeoIP overrides.
        """
        result = GeoIPResult()
        result.ip = ip
        result.source = "online"

        url = (
            f"http://ip-api.com/json/{ip}"
            "?fields=status,message,country,countryCode,regionName,city,lat,lon,timezone"
        )

        deadline = time.monotonic() + _ONLINE_TOTAL_BUDGET
        last_error: Optional[str] = None

        for attempt in range(1, _ONLINE_MAX_ATTEMPTS + 1):
            if time.monotonic() >= deadline:
                last_error = "time budget exhausted before completing"
                break

            try:
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "Huligan-GeoIP/1.0")

                with urllib.request.urlopen(req, timeout=_ONLINE_PER_ATTEMPT_TIMEOUT) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                if data.get("status") == "success":
                    result.country_code = data.get("countryCode", "")
                    result.country_name = data.get("country", "")
                    result.city = data.get("city", "")
                    result.region = data.get("regionName", "")
                    result.timezone = data.get("timezone", "")
                    result.latitude = float(data.get("lat", 0))
                    result.longitude = float(data.get("lon", 0))
                    result.accuracy = 50000  # ~50km for online API
                    result.language = COUNTRY_LANGUAGE_MAP.get(
                        result.country_code, DEFAULT_LANGUAGE
                    )
                    return result

                # Service returned 200 but reported failure (e.g. private IP
                # or rate-limit). Treat as a hard error — no point retrying.
                last_error = data.get("message", "online provider reported failure")
                break

            except (urllib.error.URLError, socket.timeout) as e:
                last_error = f"network error: {e}"
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
            except Exception as e:
                last_error = f"unexpected error: {type(e).__name__}: {e}"

            if attempt < _ONLINE_MAX_ATTEMPTS:
                backoff = _ONLINE_BACKOFF_BASE * (2 ** (attempt - 1))
                backoff += random.uniform(0, _ONLINE_BACKOFF_JITTER)
                # Never sleep past the global deadline
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(backoff, remaining))
                log.debug(f"GeoIP attempt {attempt} failed ({last_error}); retrying")

        result.error = last_error or "online lookup failed without a specific error"
        log.warning(f"GeoIP online lookup gave up for {ip}: {result.error}")
        return result

    def lookup_proxy(self, proxy_url: str) -> GeoIPResult:
        """
        Lookup proxy IP (extract host from proxy URL first).

        Supports: socks5://user:pass@host:port, http://host:port, etc.
        """
        host = self._extract_host(proxy_url)
        ip = self._resolve_host(host)
        return self.lookup(ip)

    def _extract_host(self, proxy_str: str) -> str:
        """Extract host from proxy URL."""
        proxy_str = proxy_str.strip()

        if "://" in proxy_str:
            proxy_str = proxy_str.split("://", 1)[1]

        if "@" in proxy_str:
            proxy_str = proxy_str.split("@", 1)[1]

        if proxy_str.startswith("["):
            bracket_end = proxy_str.index("]")
            return proxy_str[1:bracket_end]

        return proxy_str.split(":")[0]

    def _resolve_host(self, host: str) -> str:
        """
        Resolve hostname to IP under a strict timeout.

        ``socket.gethostbyname`` honours the *system* DNS timeout
        (often 30+ seconds) which would stall browser launch. We use
        ``getaddrinfo`` with a temporary default-timeout override so
        a slow resolver does not gate the boot.
        """
        try:
            socket.inet_aton(host)
            return host
        except socket.error:
            pass

        try:
            socket.inet_pton(socket.AF_INET6, host)
            return host
        except socket.error:
            pass

        previous = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(_DNS_TIMEOUT)
            return socket.gethostbyname(host)
        except (socket.gaierror, socket.timeout) as e:
            log.warning(f"DNS resolution for {host!r} failed: {e}")
            return host
        finally:
            socket.setdefaulttimeout(previous)

    def update_profile(self, profile_path: str, geo_result: GeoIPResult) -> bool:
        """
        Update existing profile .conf with geo data.

        Updates or adds: timezone, geolocation_latitude, geolocation_longitude, geolocation_accuracy, languages
        """
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            updates = {
                "timezone": geo_result.timezone,
                "geolocation_latitude": str(geo_result.latitude),
                "geolocation_longitude": str(geo_result.longitude),
                "geolocation_accuracy": str(geo_result.accuracy),
                "languages": geo_result.language,
            }

            updated_keys = set()
            new_lines = []

            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    key = stripped.split("=")[0] if "=" in stripped else ""
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

            return True

        except Exception:
            return False

    def close(self):
        """Close database reader."""
        if self.reader:
            self.reader.close()
