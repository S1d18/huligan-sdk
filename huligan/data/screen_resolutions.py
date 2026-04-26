"""Realistic screen resolution combinations"""

# Format: (width, height, avail_width, avail_height, device_pixel_ratio)
# avail_* accounts for taskbar/menu bar

COMMON_RESOLUTIONS = [
    # 1920x1080 (Full HD) - most common
    (1920, 1080, 1920, 1040, 1.0),    # Windows (40px taskbar)
    (1920, 1080, 1920, 1055, 1.0),    # Windows (25px taskbar)
    (1920, 1080, 1920, 1050, 2.0),    # Mac Retina (30px menu bar)

    # 2560x1440 (QHD)
    (2560, 1440, 2560, 1400, 1.0),    # Windows
    (2560, 1440, 2560, 1415, 1.0),    # Windows (slim taskbar)
    (2560, 1440, 2560, 1410, 2.0),    # Mac Retina

    # 3840x2160 (4K)
    (3840, 2160, 3840, 2120, 1.0),    # Windows
    (3840, 2160, 3840, 2135, 1.0),    # Windows (slim)
    (3840, 2160, 3840, 2130, 2.0),    # Mac Retina

    # 1366x768 (Common laptop)
    (1366, 768, 1366, 728, 1.0),      # Windows
    (1366, 768, 1366, 738, 1.0),      # Windows (slim)

    # 1536x864 (Laptop HD+)
    (1536, 864, 1536, 824, 1.0),      # Windows
    (1536, 864, 1536, 834, 1.25),     # Windows scaled

    # 1680x1050 (WSXGA+)
    (1680, 1050, 1680, 1010, 1.0),    # Windows
    (1680, 1050, 1680, 1020, 1.0),    # Mac

    # 1440x900 (WXGA+)
    (1440, 900, 1440, 860, 1.0),      # Windows
    (1440, 900, 1440, 875, 1.0),      # Mac

    # 2880x1800 (MacBook Pro 15")
    (2880, 1800, 2880, 1770, 2.0),    # Mac Retina

    # 3072x1920 (MacBook Pro 16")
    (3072, 1920, 3072, 1890, 2.0),    # Mac Retina
]

def get_random_resolution(rng=None):
    """
    Get random realistic screen resolution with weighted distribution.

    Distribution:
    - 1920x1080 (Full HD): 40% (most common)
    - 1366x768, 1536x864, 1440x900 (Laptops): 30%
    - 2560x1440 (QHD): 20%
    - 3840x2160, 2880x1800, 3072x1920 (4K/Retina): 10% (less common)

    Args:
        rng: Random number generator (uses stdlib random if None)

    Returns:
        tuple: (width, height, avail_width, avail_height, device_pixel_ratio)
    """
    if rng is None:
        import random as _random
        rng = _random

    # Weighted distribution (weights must match COMMON_RESOLUTIONS order)
    weights = [
        # 1920x1080 (Full HD) - 40% total
        15, 15, 10,
        # 2560x1440 (QHD) - 20% total
        7, 7, 6,
        # 3840x2160 (4K) - 5% total (reduced!)
        2, 2, 1,
        # 1366x768 (Laptop) - 15% total
        8, 7,
        # 1536x864 (Laptop HD+) - 8% total
        4, 4,
        # 1680x1050 (WSXGA+) - 4% total
        2, 2,
        # 1440x900 (WXGA+) - 4% total
        2, 2,
        # 2880x1800 (MacBook 15") - 2% total
        2,
        # 3072x1920 (MacBook 16") - 2% total
        2,
    ]

    return rng.choices(COMMON_RESOLUTIONS, weights=weights, k=1)[0]
