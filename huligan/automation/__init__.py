"""Human-like automation helpers for Huligan antidetect browser.

Each submodule is imported independently — installing pip extras only
for the helpers you actually use is fine. Missing dependencies in one
submodule do not break the others.

Optional deps:
- mouse, keyboard: pytweening + loguru  (pip install huligan[automation])
- scroll, idle, cdp_helpers: no extras required (only playwright)
"""

# CDP helpers — no extra deps beyond playwright
try:
    from .cdp_helpers import (
        cdp_bounding_box,
        cdp_viewport_size,
        cdp_scroll_y,
        cdp_document_height,
        cdp_is_visible,
        cdp_wait_for_visible,
        cleanup_cdp_session,
        cdp_bounding_box_locator,
    )
except ImportError:
    pass

# Scroll — no extra deps
try:
    from .scroll import human_like_scroll, human_like_scroll_to_top
except ImportError:
    pass

# Idle / reading pauses — no extra deps
try:
    from .idle import idle_mouse_movement, simulated_reading_pause
except ImportError:
    pass

# Mouse / keyboard — require pytweening + loguru
try:
    from .mouse import human_like_mouse_click
except ImportError:
    pass

try:
    from .keyboard import human_like_type, human_like_hotkey
except ImportError:
    pass
