"""
Huligan SDK — Standalone GeoIP lookup (IP -> timezone/locale/coordinates).

`Browser(proxy=...)` already runs this internally to populate the `.conf`
profile automatically — no setup needed for normal use. Reach for this
module directly when you want the IP -> geo/timezone/language mapping on
its own, decoupled from launching a browser (e.g. pre-flight-checking a
proxy list, or picking which locale template to use before you spin up
any Chrome instance).

See docs/GEOIP_SETUP.md for the local MaxMind GeoLite2 database setup
(recommended — faster, no rate limit) vs the online ip-api.com fallback
this uses automatically when no local database is found.
"""
from huligan.geoip import GeoIPManager


def main():
    manager = GeoIPManager()

    # Direct IP lookup.
    result = manager.lookup("185.156.177.1")
    print(f"source:       {result.source}")   # "local" (MaxMind) or "online" (ip-api.com)
    print(f"country:      {result.country_name} ({result.country_code})")
    print(f"city/region:  {result.city}, {result.region}")
    print(f"timezone:     {result.timezone}")
    print(f"language:     {result.language}")
    print(f"coordinates:  {result.latitude}, {result.longitude}")
    if result.error:
        print(f"error:        {result.error}")

    # Lookup straight from a proxy URL — host is extracted for you.
    print("\n--- lookup_proxy ---")
    proxy_result = manager.lookup_proxy("socks5://user:pass@185.156.177.1:1080")
    print(f"{proxy_result.city}, {proxy_result.country_name} -> {proxy_result.timezone}")

    manager.close()


if __name__ == "__main__":
    main()
