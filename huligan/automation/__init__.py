"""Human-like automation helpers for Huligan antidetect browser."""
try:
    from .mouse import human_like_mouse_click
    from .keyboard import human_like_type, human_like_hotkey
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
    pass  # Optional dependencies (pytweening, loguru)
