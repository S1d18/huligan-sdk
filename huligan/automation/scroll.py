"""
Human-like scrolling without requiring a target element.

For "scroll until element is visible" use `human_like_mouse_click` from
mouse.py which already includes humanized scroll-to-element. Use this
module when you want untargeted scrolling — e.g. simulated reading,
infinite-feed warm-up, or natural-looking page exploration.

Async and sync are selected by the module-level MODE flag (same pattern
as mouse.py and keyboard.py).
"""
# ====== РЕЖИМ РАБОТЫ ======
# "async" — для Patchright/Playwright async (с await)
# "sync"  — для обычных синхронных проектов (без await)
MODE = "async"
# ==========================

import random
from typing import Literal

if MODE == "async":
    import asyncio
    from playwright.async_api import Page
else:
    import time
    from playwright.sync_api import Page


# --- Defaults (mirror style from mouse.py SPEED_PROFILES) ---
SCROLL_PROFILES = {
    "fast": {
        "CHUNK_SIZE_RANGE": (150, 350),
        "CHUNK_DELAY_RANGE": (0.01, 0.04),
        "PAUSE_AFTER_CHUNKS": (0.03, 0.08),
        "LONG_PAUSE_PROBABILITY": 0.05,
        "LONG_PAUSE_DURATION_RANGE": (0.2, 0.6),
        "REVERSE_PROBABILITY": 0.03,
        "JITTER_PER_CHUNK": (-10, 10),
    },
    "medium": {
        "CHUNK_SIZE_RANGE": (100, 250),
        "CHUNK_DELAY_RANGE": (0.02, 0.07),
        "PAUSE_AFTER_CHUNKS": (0.06, 0.15),
        "LONG_PAUSE_PROBABILITY": 0.15,
        "LONG_PAUSE_DURATION_RANGE": (0.4, 1.2),
        "REVERSE_PROBABILITY": 0.10,
        "JITTER_PER_CHUNK": (-20, 20),
    },
    "slow": {
        "CHUNK_SIZE_RANGE": (60, 160),
        "CHUNK_DELAY_RANGE": (0.04, 0.12),
        "PAUSE_AFTER_CHUNKS": (0.1, 0.3),
        "LONG_PAUSE_PROBABILITY": 0.25,
        "LONG_PAUSE_DURATION_RANGE": (0.8, 2.5),
        "REVERSE_PROBABILITY": 0.15,
        "JITTER_PER_CHUNK": (-30, 30),
    },
}


def _resolve_profile(speed_mode: str) -> dict:
    if speed_mode not in SCROLL_PROFILES:
        speed_mode = "medium"
    return SCROLL_PROFILES[speed_mode]


def _signed_distance(direction: str, distance: int) -> int:
    if distance < 0:
        return distance  # Caller already signed it
    return -abs(distance) if direction == "up" else abs(distance)


# ==================== ASYNC ====================
if MODE == "async":

    async def human_like_scroll(
        page: Page,
        direction: Literal["up", "down"] = "down",
        distance: int = 500,
        speed_mode: Literal["fast", "medium", "slow"] = "medium",
        allow_reverse: bool = True,
    ) -> int:
        """
        Scroll the page by approximately ``distance`` pixels in chunks
        with humanized delays, jitter, and the occasional reverse-wheel.

        Distance is approximate — real humans don't scroll exact pixel
        amounts. Use ``allow_reverse=False`` for tight control.

        Args:
            page: Playwright async Page.
            direction: ``"up"`` or ``"down"``.
            distance: Approximate pixels to scroll. Always positive;
                ``direction`` controls sign.
            speed_mode: ``"fast"`` / ``"medium"`` / ``"slow"``.
            allow_reverse: If False, never emit a reverse-direction
                chunk (purely directional scrolling).

        Returns:
            Total pixels actually wheeled (signed; negative = up).
        """
        params = _resolve_profile(speed_mode)
        remaining = abs(int(distance))
        sign = -1 if direction == "up" else 1
        wheeled = 0

        while remaining > 5:
            chunk_base = random.uniform(*params["CHUNK_SIZE_RANGE"])
            chunk = int(min(chunk_base, remaining))
            chunk += random.uniform(*params["JITTER_PER_CHUNK"])
            if abs(chunk) < 5:
                chunk = 5

            # Occasional reverse chunk for naturalism
            this_sign = sign
            if allow_reverse and random.random() < params["REVERSE_PROBABILITY"]:
                this_sign = -sign

            delta = int(this_sign * chunk)
            await page.mouse.wheel(0, delta)
            wheeled += delta
            remaining -= int(chunk * 0.85)  # Reverses still cost some budget

            await asyncio.sleep(random.uniform(*params["CHUNK_DELAY_RANGE"]))

            if random.random() < params["LONG_PAUSE_PROBABILITY"]:
                await asyncio.sleep(random.uniform(*params["LONG_PAUSE_DURATION_RANGE"]))
            else:
                await asyncio.sleep(random.uniform(*params["PAUSE_AFTER_CHUNKS"]))

        return wheeled


    async def human_like_scroll_to_top(
        page: Page,
        speed_mode: Literal["fast", "medium", "slow"] = "fast",
    ) -> None:
        """
        Scroll roughly all the way up. Uses a generous fixed budget so
        most pages reach the top — works even when document height is
        unknown.
        """
        await human_like_scroll(
            page, direction="up", distance=20000,
            speed_mode=speed_mode, allow_reverse=False,
        )


# ==================== SYNC ====================
else:

    def human_like_scroll(
        page: Page,
        direction: Literal["up", "down"] = "down",
        distance: int = 500,
        speed_mode: Literal["fast", "medium", "slow"] = "medium",
        allow_reverse: bool = True,
    ) -> int:
        """Sync variant — see async docstring above."""
        params = _resolve_profile(speed_mode)
        remaining = abs(int(distance))
        sign = -1 if direction == "up" else 1
        wheeled = 0

        while remaining > 5:
            chunk_base = random.uniform(*params["CHUNK_SIZE_RANGE"])
            chunk = int(min(chunk_base, remaining))
            chunk += random.uniform(*params["JITTER_PER_CHUNK"])
            if abs(chunk) < 5:
                chunk = 5

            this_sign = sign
            if allow_reverse and random.random() < params["REVERSE_PROBABILITY"]:
                this_sign = -sign

            delta = int(this_sign * chunk)
            page.mouse.wheel(0, delta)
            wheeled += delta
            remaining -= int(chunk * 0.85)

            time.sleep(random.uniform(*params["CHUNK_DELAY_RANGE"]))

            if random.random() < params["LONG_PAUSE_PROBABILITY"]:
                time.sleep(random.uniform(*params["LONG_PAUSE_DURATION_RANGE"]))
            else:
                time.sleep(random.uniform(*params["PAUSE_AFTER_CHUNKS"]))

        return wheeled


    def human_like_scroll_to_top(
        page: Page,
        speed_mode: Literal["fast", "medium", "slow"] = "fast",
    ) -> None:
        human_like_scroll(
            page, direction="up", distance=20000,
            speed_mode=speed_mode, allow_reverse=False,
        )
