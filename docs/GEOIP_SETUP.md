# GeoIP Setup Guide

## Overview

GeoIP determines timezone, language, coordinates, and country from a proxy IP address. The SDK uses this to populate `.conf` profile fields automatically before launching Chrome.

When you call `Browser(proxy=...)`, GeoIP runs automatically. No setup needed for basic use.

## How It Works

Two methods, tried in order:

1. **Local MaxMind GeoLite2 database** — fast, offline, no limits
2. **Online API fallback** — ip-api.com, requires internet, 45 req/min limit

## Python API

```python
from huligan.geoip import GeoIPManager

manager = GeoIPManager()

# Lookup by IP
result = manager.lookup("185.156.177.1")
print(result.timezone)      # e.g. "Europe/Helsinki"
print(result.language)      # e.g. "fi-FI,fi"
print(result.latitude)      # e.g. 60.1699
print(result.longitude)     # e.g. 24.9384
print(result.country_code)  # e.g. "FI"
print(result.country_name)  # e.g. "Finland"
print(result.city)          # e.g. "Helsinki"

manager.close()

# Lookup from proxy URL (extracts IP automatically)
result = manager.lookup_proxy("socks5://user:pass@185.156.177.1:1080")
```

## Setting Up Local Database (Recommended)

The local database is faster and doesn't depend on internet connectivity.

### Step 1: Register at MaxMind

1. Go to https://www.maxmind.com/en/geolite2/signup
2. Create a free account
3. Confirm email
4. Under Account → Manage License Keys → Generate new license key

### Step 2: Install geoip2

```bash
pip install huligan[geoip]
# or directly:
pip install geoip2
```

### Step 3: Download the database

Place `GeoLite2-City.mmdb` in any of these locations (SDK checks in order):

| Location | Notes |
|----------|-------|
| `huligan/data/GeoLite2-City.mmdb` | Inside the SDK package dir |
| `data/GeoLite2-City.mmdb` | Relative to working directory |
| `C:\ProgramData\MaxMind\GeoLite2-City.mmdb` | Windows system path |
| `/usr/share/GeoIP/GeoLite2-City.mmdb` | Linux system path |
| `/var/lib/GeoIP/GeoLite2-City.mmdb` | Linux alternative |

Download script:
```python
from huligan.geoip import GeoIPManager

# Downloads to huligan/data/GeoLite2-City.mmdb
manager = GeoIPManager()
manager.download_db("YOUR_MAXMIND_LICENSE_KEY")
manager.close()
```

Or manually:
1. Download from https://dev.maxmind.com/geoip/geoip2/geolite2/
2. Extract `GeoLite2-City.mmdb`
3. Place in one of the paths above

### Step 4: Verify

```python
from huligan.geoip import GeoIPManager

manager = GeoIPManager()
result = manager.lookup("8.8.8.8")
print(result.country_code)  # "US"
manager.close()
```

## Country → Language Mapping

The SDK maps country code to `navigator.language` / `--lang` automatically:

| Country | Language |
|---------|----------|
| US | en-US,en |
| GB | en-GB,en |
| DE | de-DE,de |
| FR | fr-FR,fr |
| FI | fi-FI,fi |
| RU | ru-RU,ru |
| UA | uk-UA,uk |
| JP | ja-JP,ja |
| CN | zh-CN,zh |
| ... | ... |

Full mapping: `huligan/geoip.py` → `COUNTRY_LANGUAGE_MAP`.

## Auto-Update Database

MaxMind updates GeoLite2 every 2 weeks. Schedule an update:

**Windows Task Scheduler:**
```batch
schtasks /create /tn "Update GeoIP" /tr "python -c \"from huligan.geoip import GeoIPManager; m=GeoIPManager(); m.download_db('LICENSE_KEY'); m.close()\"" /sc weekly
```

**Linux cron:**
```bash
0 3 * * 0 python -c "from huligan.geoip import GeoIPManager; m=GeoIPManager(); m.download_db('LICENSE_KEY'); m.close()"
```

## Troubleshooting

### "geoip2 not installed"

```bash
pip install huligan[geoip]
```

### "No local database found, using online fallback"

GeoIP falls back to ip-api.com automatically. This is normal if you haven't set up the local database. Performance is slower and subject to rate limits.

### "IP not found in local DB"

Private/reserved IPs (10.x, 192.168.x) are not in the database. The SDK will attempt the online fallback. If the online API also fails, timezone defaults to `UTC` and language to `en-US,en`.

### Rate limit hit (online API)

ip-api.com allows 45 requests/minute on the free tier. For high-volume use, install the local database.
