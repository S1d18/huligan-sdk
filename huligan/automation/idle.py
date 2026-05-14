"""
Idle-time humanizing behaviours.

Real users don't sit perfectly still while reading a page. Modern
behavioural biometrics (reCAPTCHA v3, FingerprintJS Pro behaviour
signal, Cloudflare Turnstile) downgrade their trust score when the
mouse is motionless for long stretches. ``idle_mouse_movement`` keeps
the cursor doing tiny natural jitters during deliberate pauses.

Pair with ``simulated_reading_pause`` when you want a fixed-duration
"the user is reading this" delay that includes the idle jitter.
"""
# ====== РЕЖИМ РАБОТЫ ======
MODE = "async"
# ==========================

import math
import random
from typing import Literal

if MODE == "async":
    import asyncio
    from playwright.async_api import Page
else:
    import time
    from playwright.sync_api import Page


# --- Tunables per intensity preset ---
IDLE_PROFILES = {
    "subtle": {
        # 1-3 px micro-movements, infrequent
        "RADIUS_RANGE": (1, 4),
        "MOVES_PER_SECOND": 0.8,
        "STEP_DELAY_RANGE": (0.02, 0.05),
        "INTER_MOVE_PAUSE_RANGE": (0.4, 1.2),
    },
    "natural": {
        # 3-12 px, more frequent — mimics light hand resting
        "RADIUS_RANGE": (2, 12),
        "MOVES_PER_SECOND": 1.6,
        "STEP_DELAY_RANGE": (0.015, 0.04),
        "INTER_MOVE_PAUSE_RANGE": (0.2, 0.7),
    },
    "active": {
        # 8-30 px, often — mimics restless hand
        "RADIUS_RANGE": (5, 30),
        "MOVES_PER_SECOND": 2.5,
        "STEP_DELAY_RANGE": (0.012, 0.03),
        "INTER_MOVE_PAUSE_RANGE": (0.1, 0.5),
    },
}


def _resolve(intensity: str) -> dict:
    return IDLE_PROFILES.get(intensity, IDLE_PROFILES["natural"])


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _next_point(cx: float, cy: float, params: dict,
                bounds: tuple) -> tuple:
    """Pick the next jitter target around (cx, cy) within bounds."""
    angle = random.uniform(0, 2 * math.pi)
    r = random.uniform(*params["RADIUS_RANGE"])
    tx = cx + r * math.cos(angle)
    ty = cy + r * math.sin(angle)
    bx, by = bounds
    return _clamp(tx, 0, bx - 1), _clamp(ty, 0, by - 1)


# ==================== ASYNC ====================
if MODE == "async":

    async def _get_viewport(page: Page) -> tuple:
        vp = page.viewport_size
        if vp:
            return vp["width"], vp["height"]
        return 1280, 720


    async def idle_mouse_movement(
        page: Page,
        duration_s: float = 2.0,
        intensity: Literal["subtle", "natural", "active"] = "natural",
        anchor: tuple = None,
    ) -> tuple:
        """
        Jitter the cursor with small natural moves for ``duration_s``.

        Use this during reading-like pauses (e.g. after navigating to a
        new page, before submitting a form, between actions on a long
        page) to avoid the "motionless cursor" signal that behavioural
        antibots flag.

        Args:
            page: Playwright async Page.
            duration_s: Total time to spend jittering.
            intensity: ``"subtle"`` / ``"natural"`` / ``"active"``.
            anchor: ``(x, y)`` pixel coordinates to drift around. If
                ``None``, drifts around the viewport centre.

        Returns:
            Final ``(x, y)`` of the cursor.
        """
        params = _resolve(intensity)
        vw, vh = await _get_viewport(page)
        if anchor is None:
            cx, cy = vw / 2, vh / 2
        else:
            cx, cy = anchor

        deadline = asyncio.get_event_loop().time() + duration_s

        while asyncio.get_event_loop().time() < deadline:
            tx, ty = _next_point(cx, cy, params, (vw, vh))

            # Tweened move in a few small steps for smoothness
            steps = random.randint(2, 4)
            dx = (tx - cx) / steps
            dy = (ty - cy) / steps
            for i in range(steps):
                cx += dx
                cy += dy
                await page.mouse.move(round(cx), round(cy))
                await asyncio.sleep(random.uniform(*params["STEP_DELAY_RANGE"]))

            cx, cy = tx, ty
            await asyncio.sleep(random.uniform(*params["INTER_MOVE_PAUSE_RANGE"]))

        return cx, cy


    async def simulated_reading_pause(
        page: Page,
        words: int = 60,
        wpm: int = 220,
        intensity: Literal["subtle", "natural", "active"] = "natural",
    ) -> None:
        """
        Pause as if reading ``words`` words at ``wpm`` words per minute,
        keeping the cursor alive with ``idle_mouse_movement``.

        Defaults to 220 wpm (typical adult silent-reading speed for
        web content) and 60 words. Tune for the content the user would
        plausibly be skimming.
        """
        seconds = max(0.5, (words / max(wpm, 1)) * 60.0)
        await idle_mouse_movement(page, duration_s=seconds, intensity=intensity)


# ==================== SYNC ====================
else:

    def _get_viewport(page: Page) -> tuple:
        vp = page.viewport_size
        if vp:
            return vp["width"], vp["height"]
        return 1280, 720


    def idle_mouse_movement(
        page: Page,
        duration_s: float = 2.0,
        intensity: Literal["subtle", "natural", "active"] = "natural",
        anchor: tuple = None,
    ) -> tuple:
        """Sync variant — see async docstring above."""
        params = _resolve(intensity)
        vw, vh = _get_viewport(page)
        if anchor is None:
            cx, cy = vw / 2, vh / 2
        else:
            cx, cy = anchor

        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            tx, ty = _next_point(cx, cy, params, (vw, vh))
            steps = random.randint(2, 4)
            dx = (tx - cx) / steps
            dy = (ty - cy) / steps
            for i in range(steps):
                cx += dx
                cy += dy
                page.mouse.move(round(cx), round(cy))
                time.sleep(random.uniform(*params["STEP_DELAY_RANGE"]))
            cx, cy = tx, ty
            time.sleep(random.uniform(*params["INTER_MOVE_PAUSE_RANGE"]))

        return cx, cy


    def simulated_reading_pause(
        page: Page,
        words: int = 60,
        wpm: int = 220,
        intensity: Literal["subtle", "natural", "active"] = "natural",
    ) -> None:
        seconds = max(0.5, (words / max(wpm, 1)) * 60.0)
        idle_mouse_movement(page, duration_s=seconds, intensity=intensity)
