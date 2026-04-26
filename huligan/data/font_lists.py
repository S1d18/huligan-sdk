"""
Font lists for Windows/Mac/Linux platforms
Based on official Microsoft, Apple, and Linux font catalogs
"""

# === WINDOWS 10/11 FONTS ===
# Source: https://learn.microsoft.com/en-us/typography/fonts/windows_10_font_list

# CORE fonts - ALWAYS present (critical for UI and web rendering)
CORE_WINDOWS_FONTS = [
    # Critical for Windows UI
    "Segoe UI",
    "Segoe UI Symbol",
    "Segoe UI Emoji",
    "Segoe MDL2 Assets",

    # Critical for web rendering
    "Arial",
    "Times New Roman",
    "Courier New",
    "Verdana",
    "Georgia",
    "Tahoma",
    "Calibri",
    "Trebuchet MS",
    "Impact",
    "Comic Sans MS",
    "Consolas",
]

# STANDARD Windows 10 fonts (always pre-installed)
STANDARD_WINDOWS_FONTS = [
    "Arial Black",
    "Bahnschrift",
    "Cambria",
    "Cambria Math",
    "Candara",
    "Constantia",
    "Corbel",
    "Ebrima",
    "Franklin Gothic Medium",
    "Gabriola",
    "Gadugi",
    "HoloLens MDL2 Assets",
    "Ink Free",
    "Javanese Text",
    "Leelawadee UI",
    "Lucida Console",
    "Lucida Sans Unicode",
    "Malgun Gothic",
    "Marlett",
    "Microsoft Himalaya",
    "Microsoft JhengHei",
    "Microsoft New Tai Lue",
    "Microsoft PhagsPa",
    "Microsoft Sans Serif",
    "Microsoft Tai Le",
    "Microsoft YaHei",
    "Microsoft Yi Baiti",
    "MingLiU-ExtB",
    "Mongolian Baiti",
    "MS Gothic",
    "MV Boli",
    "Myanmar Text",
    "Nirmala UI",
    "Palatino Linotype",
    "Segoe Print",
    "Segoe Script",
    "Segoe UI Historic",
    "SimSun",
    "Sitka",
    "Sylfaen",
    "Symbol",
    "Webdings",
    "Wingdings",
    "Yu Gothic",
]

# Feature On Demand (FOD) fonts - optional but commonly installed
FOD_WINDOWS_FONTS = [
    # Arabic Script
    "Aldhabi", "Andalus", "Arabic Typesetting", "Microsoft Uighur",
    "Sakkal Majalla", "Simplified Arabic", "Traditional Arabic", "Urdu Typesetting",

    # Bangla Script
    "Shonar Bangla", "Vrinda",

    # Canadian Aboriginal Syllabics
    "Euphemia",

    # Cherokee
    "Plantagenet Cherokee",

    # Devanagari
    "Aparajita", "Kokila", "Mangal", "Sanskrit Text", "Utsaah",

    # Ethiopic
    "Nyala",

    # Gujarati
    "Shruti",

    # Gurmukhi
    "Raavi",

    # Chinese Simplified
    "DengXian", "FangSong", "KaiTi", "SimHei",

    # Chinese Traditional
    "DFKai-SB", "MingLiU", "PMingLiU",

    # Hebrew
    "Aharoni Bold", "David", "FrankRuehl", "Gisha", "Levenim MT",
    "Miriam", "Narkisim", "Rod",

    # Japanese
    "BIZ UDGothic", "BIZ UDMincho Medium", "Meiryo", "MS Mincho",
    "UD Digi Kyokasho", "Yu Mincho",

    # Kannada
    "Tunga",

    # Khmer
    "DaunPenh", "Khmer UI", "MoolBoran",

    # Korean
    "Batang", "Dotum", "Gulim", "Gungsuh",

    # Lao
    "DokChampa", "Lao UI",

    # Malayalam
    "Kartika",

    # Odia
    "Kalinga",

    # Pan-European
    "Arial Nova", "Georgia Pro", "Gill Sans Nova",
    "Neue Haas Grotesk Text Pro", "Rockwell Nova", "Verdana Pro",

    # Sinhala
    "Iskoola Pota",

    # Syriac
    "Estrangelo Edessa",

    # Tamil
    "Latha", "Vijaya",

    # Telugu
    "Gautami", "Vani",

    # Thai
    "Angsana New", "AngsanaUPC", "Browallia New", "BrowalliaUPC",
    "Cordia New", "CordiaUPC", "DilleniaUPC", "EucrosiaUPC",
    "FreesiaUPC", "IrisUPC", "JasmineUPC", "KodchiangUPC",
    "Leelawadee", "LilyUPC",
]

# macOS fonts
MACOS_FONTS = [
    # San Francisco (system font)
    "SF Pro Display", "SF Pro Text", "SF Compact Display", "SF Compact Text",
    "SF Mono",

    # Classic Mac fonts
    "American Typewriter", "Andale Mono", "Arial", "Arial Black",
    "Arial Narrow", "Arial Rounded MT Bold", "Arial Unicode MS",
    "Avenir", "Avenir Next", "Avenir Next Condensed",
    "Baskerville", "Big Caslon", "Bodoni 72", "Bodoni 72 Oldstyle",
    "Bodoni 72 Smallcaps", "Bradley Hand", "Brush Script MT",
    "Chalkboard", "Chalkboard SE", "Chalkduster", "Charter",
    "Cochin", "Comic Sans MS", "Copperplate", "Courier",
    "Courier New", "Didot", "Futura", "Geneva", "Georgia",
    "Gill Sans", "Helvetica", "Helvetica Neue", "Herculanum",
    "Hoefler Text", "Impact", "Lucida Grande", "Luminari",
    "Marker Felt", "Menlo", "Monaco", "Noteworthy", "Optima",
    "Palatino", "Papyrus", "Phosphate", "Rockwell", "Savoye LET",
    "SignPainter", "Skia", "Snell Roundhand", "Tahoma",
    "Times", "Times New Roman", "Trebuchet MS", "Verdana",
    "Zapfino",
]

# Linux fonts (common across major distributions)
LINUX_FONTS = [
    # DejaVu family (most common)
    "DejaVu Sans", "DejaVu Sans Mono", "DejaVu Serif",
    "DejaVu Sans Condensed", "DejaVu Serif Condensed",

    # Liberation family (RedHat/Fedora)
    "Liberation Sans", "Liberation Serif", "Liberation Mono",
    "Liberation Sans Narrow",

    # Ubuntu family
    "Ubuntu", "Ubuntu Condensed", "Ubuntu Mono", "Ubuntu Light",

    # Noto family (Google)
    "Noto Sans", "Noto Serif", "Noto Mono", "Noto Sans Display",
    "Noto Serif Display",

    # Droid family (Android/Linux)
    "Droid Sans", "Droid Serif", "Droid Sans Mono",

    # GNU FreeFont
    "FreeSans", "FreeSerif", "FreeMono",

    # Bitstream Vera (classic)
    "Bitstream Vera Sans", "Bitstream Vera Serif", "Bitstream Vera Sans Mono",

    # Common system fonts
    "Cantarell", "Oxygen", "Oxygen Mono", "Roboto", "Roboto Condensed",
    "Roboto Mono", "Roboto Slab", "Source Code Pro", "Source Sans Pro",
    "Source Serif Pro", "Terminus", "PT Sans", "PT Serif", "PT Mono",
    "Inconsolata", "Hack",
]


def get_random_fonts(platform="Win32", count=None, rng=None):
    """
    Get realistic font list for platform with randomization.

    For Windows:
    - Always include 59 base fonts (15 CORE + 44 STANDARD)
    - Add 20-100 random FOD fonts
    - Total: 79-159 fonts (realistic range)

    Args:
        platform: "Win32", "MacIntel", or "Linux x86_64"
        count: Total fonts to return (None = auto random 79-159 for Windows)
        rng: Random number generator (uses stdlib random if None)

    Returns:
        list: Font family names
    """
    if rng is None:
        import random as _random
        rng = _random

    if platform == "Win32":
        # Always include all base Windows fonts (59 fonts)
        base_fonts = CORE_WINDOWS_FONTS + STANDARD_WINDOWS_FONTS

        # Determine how many additional fonts to add
        if count is None:
            # Random count 79-159 (20-100 additional FOD fonts)
            additional_count = rng.randint(20, 100)
        else:
            # User specified total count
            additional_count = max(0, count - len(base_fonts))

        # Add random FOD fonts
        if additional_count > 0 and FOD_WINDOWS_FONTS:
            additional = rng.sample(
                FOD_WINDOWS_FONTS,
                min(additional_count, len(FOD_WINDOWS_FONTS))
            )
            all_fonts = base_fonts + additional
        else:
            all_fonts = base_fonts

        # Shuffle to make order random (but keep all base fonts)
        rng.shuffle(all_fonts)
        return all_fonts

    elif platform == "MacIntel":
        # macOS: use all mac fonts + small random subset
        if count is None:
            count = rng.randint(50, len(MACOS_FONTS))

        # Always include some core Mac fonts
        core_mac = ["SF Pro Text", "Helvetica Neue", "Arial", "Times New Roman",
                    "Courier New", "Verdana", "Georgia", "Monaco", "Menlo"]

        # Random additional fonts
        additional_pool = [f for f in MACOS_FONTS if f not in core_mac]
        additional_count = min(count - len(core_mac), len(additional_pool))

        if additional_count > 0:
            additional = rng.sample(additional_pool, additional_count)
            all_fonts = core_mac + additional
        else:
            all_fonts = core_mac

        rng.shuffle(all_fonts)
        return all_fonts

    else:  # Linux
        # Linux: use all available fonts
        if count is None:
            count = rng.randint(45, len(LINUX_FONTS))

        # Always include some core Linux fonts
        core_linux = ["DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono",
                      "Liberation Sans", "Liberation Serif", "Liberation Mono",
                      "Ubuntu", "FreeSans", "FreeSerif"]

        # Random additional fonts
        additional_pool = [f for f in LINUX_FONTS if f not in core_linux]
        additional_count = min(count - len(core_linux), len(additional_pool))

        if additional_count > 0:
            additional = rng.sample(additional_pool, additional_count)
            all_fonts = core_linux + additional
        else:
            all_fonts = core_linux

        rng.shuffle(all_fonts)
        return all_fonts
