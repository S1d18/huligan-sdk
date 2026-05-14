# Huligan SDK — Notices

Huligan SDK
Copyright 2026 Huligan Project (https://github.com/S1d18)

This product includes software developed by the Huligan Project.
Licensed under the Apache License, Version 2.0 (see LICENSE).

---

## Third-Party Components

The following third-party libraries are required or optionally used by
this SDK. Each remains under its own license — installing the SDK does
not change those terms. Users redistributing this SDK alongside any
listed component must comply with that component's license.

### Required dependencies

| Package | License | Project |
|---------|---------|---------|
| `tqdm` | MPL 2.0 / MIT | https://github.com/tqdm/tqdm |

### Optional extras

| Package | License | Project | Extra |
|---------|---------|---------|-------|
| `playwright` | Apache 2.0 | https://github.com/microsoft/playwright-python | `[playwright]` |
| `geoip2` | Apache 2.0 | https://github.com/maxmind/GeoIP2-python | `[geoip]` |
| `pytweening` | MIT | https://github.com/asweigart/pytweening | `[automation]` |
| `loguru` | MIT | https://github.com/Delgan/loguru | `[automation]` |

### GeoIP data (downloaded at runtime, if `[geoip]` is installed)

The SDK can use the MaxMind **GeoLite2** database for IP geolocation.
GeoLite2 is distributed by MaxMind, Inc. under the **Creative Commons
Attribution-ShareAlike 4.0 International License**. Users are
responsible for accepting MaxMind's terms of service and providing
attribution per CC BY-SA 4.0 when redistributing the database.

GeoLite2 attribution string:

> This product includes GeoLite2 data created by MaxMind, available from
> https://www.maxmind.com.

The database is downloaded on demand; it is not bundled with this SDK.

---

## Related Huligan Components (NOT covered by this license)

| Component | Repository | License |
|-----------|------------|---------|
| Patched Chromium binary | https://github.com/S1d18/huligan-releases | Custom EULA — see that repo's `LICENSE.txt` |
| Chromium patch source | private | All rights reserved (not publicly distributed) |
| Huligan desktop GUI (`huligan-app`) | private | All rights reserved |

The SDK is licensed under Apache 2.0. The Huligan **binary** distributed
through `huligan-releases` is **NOT** licensed under Apache 2.0 — it has
its own custom End-User License Agreement that restricts redistribution
and SaaS-bundling. Read `huligan-releases/LICENSE.txt` before bundling
the binary into a product.

---

## Trademark

"Huligan" and the Huligan logo are unregistered trademarks of the
Huligan Project. Use of the name in marketing, product naming, or
derivative-product branding requires separate permission. The Apache 2.0
license expressly does not grant trademark rights (see Section 6 of the
License).
