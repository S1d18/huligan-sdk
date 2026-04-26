"""
Realistic GPU vendor/renderer combinations for Chrome/ANGLE.

Data sources:
- fingerprint-chromium (adryfish) — 57 NVIDIA models with PCI device IDs
- NVIDIA driver 570.144 supported chips list
- devicehunt.com PCI vendor 10DE
- Real Chrome ANGLE renderer string format
"""

# Format: (model_name, device_id)
# device_id with zero-padding as Chrome ANGLE reports it

# === NVIDIA RTX 3050 Series ===
NVIDIA_RTX_3050 = [
    ("GeForce RTX 3050", "0x00002507"),
    ("GeForce RTX 3050", "0x00002582"),
    ("GeForce RTX 3050 6GB Laptop GPU", "0x000025EC"),
    ("GeForce RTX 3050 Laptop GPU", "0x000025A2"),
    ("GeForce RTX 3050 Ti Laptop GPU", "0x000025A0"),
]

# === NVIDIA RTX 3060 Series ===
NVIDIA_RTX_3060 = [
    ("GeForce RTX 3060", "0x00002487"),
    ("GeForce RTX 3060", "0x00002503"),
    ("GeForce RTX 3060", "0x00002504"),
    ("GeForce RTX 3060 Laptop GPU", "0x00002520"),
    ("GeForce RTX 3060 Laptop GPU", "0x00002560"),
    ("GeForce RTX 3060 Ti", "0x00002486"),
    ("GeForce RTX 3060 Ti", "0x00002489"),
    ("GeForce RTX 3060 Ti", "0x000024C9"),
]

# === NVIDIA RTX 3070 Series ===
NVIDIA_RTX_3070 = [
    ("GeForce RTX 3070", "0x00002484"),
    ("GeForce RTX 3070", "0x00002488"),
    ("GeForce RTX 3070 Ti", "0x00002482"),
    ("GeForce RTX 3070 Ti Laptop GPU", "0x000024A0"),
]

# === NVIDIA RTX 3080 Series ===
NVIDIA_RTX_3080 = [
    ("GeForce RTX 3080", "0x00002206"),
    ("GeForce RTX 3080", "0x0000220A"),
    ("GeForce RTX 3080", "0x00002216"),
    ("GeForce RTX 3080 Laptop GPU", "0x0000249C"),
    ("GeForce RTX 3080 Laptop GPU", "0x000024DC"),
    ("GeForce RTX 3080 Ti", "0x00002208"),
    ("GeForce RTX 3080 Ti Laptop GPU", "0x00002420"),
    ("GeForce RTX 3080 Ti Laptop GPU", "0x00002460"),
]

# === NVIDIA RTX 3090 Series ===
NVIDIA_RTX_3090 = [
    ("GeForce RTX 3090", "0x00002204"),
    ("GeForce RTX 3090 Ti", "0x00002203"),
]

# === NVIDIA RTX 4050 Series ===
NVIDIA_RTX_4050 = [
    ("GeForce RTX 4050 Laptop GPU", "0x000028A1"),
    ("GeForce RTX 4050 Laptop GPU", "0x000028E1"),
]

# === NVIDIA RTX 4060 Series ===
NVIDIA_RTX_4060 = [
    ("GeForce RTX 4060", "0x00002882"),
    ("GeForce RTX 4060 Laptop GPU", "0x000028A0"),
    ("GeForce RTX 4060 Laptop GPU", "0x000028E0"),
    ("GeForce RTX 4060 Ti", "0x00002803"),
    ("GeForce RTX 4060 Ti", "0x00002805"),
]

# === NVIDIA RTX 4070 Series ===
NVIDIA_RTX_4070 = [
    ("GeForce RTX 4070", "0x00002786"),
    ("GeForce RTX 4070 Laptop GPU", "0x00002820"),
    ("GeForce RTX 4070 Laptop GPU", "0x00002860"),
    ("GeForce RTX 4070 SUPER", "0x00002783"),
    ("GeForce RTX 4070 Ti", "0x00002782"),
    ("GeForce RTX 4070 Ti SUPER", "0x00002705"),
]

# === NVIDIA RTX 4080 Series ===
NVIDIA_RTX_4080 = [
    ("GeForce RTX 4080", "0x00002704"),
    ("GeForce RTX 4080 Laptop GPU", "0x000027A0"),
    ("GeForce RTX 4080 Laptop GPU", "0x000027E0"),
    ("GeForce RTX 4080 SUPER", "0x00002702"),
]

# === NVIDIA RTX 4090 Series ===
NVIDIA_RTX_4090 = [
    ("GeForce RTX 4090", "0x00002684"),
    ("GeForce RTX 4090 Laptop GPU", "0x00002717"),
    ("GeForce RTX 4090 Laptop GPU", "0x00002757"),
]

# === NVIDIA RTX 5070 Series ===
NVIDIA_RTX_5070 = [
    ("GeForce RTX 5070", "0x00002F04"),
    ("GeForce RTX 5070 Ti", "0x00002C05"),
    ("GeForce RTX 5070 Ti Laptop GPU", "0x00002F18"),
    ("GeForce RTX 5070 Ti Laptop GPU", "0x00002F58"),
]

# === NVIDIA RTX 5080 Series ===
NVIDIA_RTX_5080 = [
    ("GeForce RTX 5080", "0x00002C02"),
    ("GeForce RTX 5080 Laptop GPU", "0x00002C19"),
    ("GeForce RTX 5080 Laptop GPU", "0x00002C59"),
]

# === NVIDIA RTX 5090 Series ===
NVIDIA_RTX_5090 = [
    ("GeForce RTX 5090", "0x00002B85"),
    ("GeForce RTX 5090 Laptop GPU", "0x00002C18"),
    ("GeForce RTX 5090 Laptop GPU", "0x00002C58"),
]

# === NVIDIA GTX (older but still common) ===
NVIDIA_GTX = [
    ("GeForce GTX 1050 Ti", "0x00001C82"),
    ("GeForce GTX 1650", "0x00001F82"),
    ("GeForce GTX 1660 Ti", "0x00002182"),
    ("GeForce GTX 1660 SUPER", "0x000021C4"),
    ("GeForce GTX 1070", "0x00001B81"),
    ("GeForce GTX 1080", "0x00001B80"),
    ("GeForce GTX 1080 Ti", "0x00001B06"),
]

# All NVIDIA models combined
NVIDIA_ALL = (
    NVIDIA_RTX_3050 + NVIDIA_RTX_3060 + NVIDIA_RTX_3070 +
    NVIDIA_RTX_3080 + NVIDIA_RTX_3090 +
    NVIDIA_RTX_4050 + NVIDIA_RTX_4060 + NVIDIA_RTX_4070 +
    NVIDIA_RTX_4080 + NVIDIA_RTX_4090 +
    NVIDIA_RTX_5070 + NVIDIA_RTX_5080 + NVIDIA_RTX_5090 +
    NVIDIA_GTX
)

# === AMD Discrete ===
AMD_DISCRETE_MODELS = [
    ("Radeon RX 7900 XTX", "0x0000744C"),
    ("Radeon RX 7800 XT", "0x0000747E"),
    ("Radeon RX 7700 XT", "0x00007479"),
    ("Radeon RX 7600", "0x00007480"),
    ("Radeon RX 6700 XT", "0x000073DF"),
    ("Radeon RX 6600 XT", "0x000073FF"),
    ("Radeon RX 5700 XT", "0x0000731F"),
    ("Radeon RX 5600 XT", "0x0000731F"),
]

# === AMD Integrated ===
AMD_INTEGRATED_MODELS = [
    ("Radeon(TM) Graphics", "0x00001681"),  # Ryzen 7000
    ("Radeon 780M", "0x00001900"),  # Ryzen 8000
    ("Radeon 680M", "0x00001681"),
    ("Radeon 660M", "0x00001638"),
    ("Radeon Vega 8 Graphics", "0x000015D8"),
    ("Radeon Vega 7 Graphics", "0x000015DD"),
    ("Radeon Vega 11 Graphics", "0x000015DD"),
]

# === Intel Integrated ===
INTEL_INTEGRATED_MODELS = [
    ("Iris(R) Xe Graphics", "0x00009A49"),
    ("UHD Graphics 770", "0x00004680"),
    ("UHD Graphics 730", "0x00004690"),
    ("UHD Graphics", "0x00009BC8"),
    ("UHD Graphics 630", "0x00003E92"),
    ("UHD Graphics 620", "0x00005917"),
    ("Iris(R) Plus Graphics", "0x00008A52"),
    ("HD Graphics 630", "0x00005912"),
    ("HD Graphics 620", "0x00005916"),
    ("HD Graphics 530", "0x00001912"),
]

# === Intel Discrete ===
INTEL_DISCRETE_MODELS = [
    ("Arc(TM) A770 Graphics", "0x000056A0"),
    ("Arc(TM) A750 Graphics", "0x000056A1"),
    ("Arc(TM) A580 Graphics", "0x000056A5"),
]

# === Apple Silicon (macOS only) ===
APPLE_SILICON = [
    "M1", "M1 Pro", "M2", "M2 Max", "M2 Pro",
    "M3", "M3 Max", "M3 Pro", "M4", "M4 Max", "M4 Pro",
]


# === ANGLE Renderer String Formatters ===

def format_nvidia_renderer_win(model_name: str, device_id: str) -> str:
    """Windows ANGLE D3D11 format for NVIDIA"""
    return f"ANGLE (NVIDIA, NVIDIA {model_name} ({device_id}) Direct3D11 vs_5_0 ps_5_0, D3D11)"

def format_nvidia_renderer_linux(model_name: str) -> str:
    """Linux ANGLE OpenGL format for NVIDIA"""
    return f"ANGLE (NVIDIA Corporation, NVIDIA {model_name}/PCIe/SSE2, OpenGL 4.5.0)"

def format_amd_renderer_win(model_name: str, device_id: str) -> str:
    """Windows ANGLE D3D11 format for AMD"""
    return f"ANGLE (AMD, AMD {model_name} ({device_id}) Direct3D11 vs_5_0 ps_5_0, D3D11)"

def format_amd_renderer_linux(model_name: str) -> str:
    """Linux ANGLE OpenGL format for AMD"""
    return f"ANGLE (AMD, AMD {model_name}, OpenGL 4.6)"

def format_intel_renderer_win(model_name: str, device_id: str) -> str:
    """Windows ANGLE D3D11 format for Intel"""
    return f"ANGLE (Intel, Intel(R) {model_name} ({device_id}) Direct3D11 vs_5_0 ps_5_0, D3D11)"

def format_intel_renderer_linux(model_name: str) -> str:
    """Linux ANGLE OpenGL format for Intel"""
    return f"ANGLE (Intel Open Source Technology Center, Intel(R) {model_name}, OpenGL 4.5)"

def format_apple_renderer(chip: str) -> str:
    """macOS Metal format for Apple Silicon"""
    return f"ANGLE (Apple, ANGLE Metal Renderer: Apple {chip}, Unspecified Version)"


# === GL_VENDOR per platform ===
GL_VENDORS = {
    "nvidia_win": "Google Inc. (NVIDIA)",
    "nvidia_linux": "Google Inc. (NVIDIA Corporation)",
    "amd_win": "Google Inc. (AMD)",
    "amd_linux": "Google Inc. (AMD)",
    "intel_win": "Google Inc. (Intel)",
    "intel_linux": "Google Inc. (Intel Open Source Technology Center)",
    "apple": "Google Inc. (Apple)",
}


# === Main API ===

# Legacy tuples format: (vendor_string, renderer_string, device_id)
# For backward compatibility with existing code

NVIDIA_DISCRETE = [
    ("Google Inc. (NVIDIA)", format_nvidia_renderer_win(m, d), d)
    for m, d in NVIDIA_RTX_4060 + NVIDIA_RTX_4070 + NVIDIA_RTX_3060 + NVIDIA_RTX_3070
]

AMD_DISCRETE = [
    ("Google Inc. (AMD)", format_amd_renderer_win(m, d), d)
    for m, d in AMD_DISCRETE_MODELS
]

INTEL_DISCRETE = [
    ("Google Inc. (Intel)", format_intel_renderer_win(m, d), d)
    for m, d in INTEL_DISCRETE_MODELS
]

INTEL_INTEGRATED = [
    ("Google Inc. (Intel)", format_intel_renderer_win(m, d), d)
    for m, d in INTEL_INTEGRATED_MODELS
]

AMD_INTEGRATED = [
    ("Google Inc. (AMD)", format_amd_renderer_win(m, d), d)
    for m, d in AMD_INTEGRATED_MODELS
]

# Legacy aliases
NVIDIA_GPUS = NVIDIA_DISCRETE
AMD_GPUS = AMD_DISCRETE
INTEL_GPUS = INTEL_INTEGRATED


def get_random_gpu(vendor_preference=None, rng=None):
    """
    Get random GPU combination with realistic distribution.

    Distribution when vendor_preference is None:
    - 60% integrated graphics (Intel UHD/Iris, AMD Vega)
    - 40% discrete graphics (NVIDIA GTX/RTX, AMD RX, Intel Arc)

    Args:
        vendor_preference: "nvidia", "amd", "intel", or None for weighted random
        rng: Random number generator (uses stdlib random if None)

    Returns:
        tuple: (vendor, renderer, device_id)
    """
    if rng is None:
        import random as _random
        rng = _random

    if vendor_preference == "nvidia":
        return rng.choice(NVIDIA_DISCRETE)
    elif vendor_preference == "amd":
        return rng.choice(AMD_DISCRETE + AMD_INTEGRATED)
    elif vendor_preference == "intel":
        return rng.choice(INTEL_DISCRETE + INTEL_INTEGRATED)
    else:
        # Realistic distribution: 60% integrated, 40% discrete
        gpu_type = rng.choices(["integrated", "discrete"], weights=[60, 40], k=1)[0]

        if gpu_type == "integrated":
            vendor = rng.choices(["intel", "amd"], weights=[70, 30], k=1)[0]
            if vendor == "intel":
                return rng.choice(INTEL_INTEGRATED)
            else:
                return rng.choice(AMD_INTEGRATED)
        else:
            vendor = rng.choices(["nvidia", "amd", "intel"], weights=[60, 30, 10], k=1)[0]
            if vendor == "nvidia":
                return rng.choice(NVIDIA_DISCRETE)
            elif vendor == "amd":
                return rng.choice(AMD_DISCRETE)
            else:
                return rng.choice(INTEL_DISCRETE)
