    # ====== РЕЖИМ РАБОТЫ ======
# "async" — для Patchright/Playwright async (с await)
# "sync" — для обычных синхронных проектов (без await)
MODE = "async"
# ==========================

import random
import sys
from typing import Literal
from loguru import logger

IS_MAC = sys.platform == "darwin"

# Условный импорт в зависимости от режима
if MODE == "async":
    import asyncio
    from playwright.async_api import Locator, Page, Keyboard
else:
    import time
    from playwright.sync_api import Locator, Page, Keyboard

# === Параметры по умолчанию (для режима "manual") ===

# --- Базовая скорость и стиль набора ---
KEY_PRESS_DELAY_RANGE = (0.04, 0.12)
KEY_DOWN_DURATION_RANGE = (0.01, 0.04)

# --- "Очеловечивание" процесса набора ---
MISTAKE_PROBABILITY = 0.1
MISTAKE_CORRECTION_DELAY_RANGE = (0.1, 0.4)
BACKSPACE_DELAY_RANGE = (0.05, 0.15)
DOUBLE_CHAR_PROBABILITY = 0.01

# --- Паузы во время набора ---
WORD_PAUSE_PROBABILITY = 0.10
WORD_PAUSE_DURATION_RANGE = (0.1, 0.5)
LONG_PAUSE_PROBABILITY = 0.01
LONG_PAUSE_DURATION_RANGE = (0.8, 2.5)

# --- Chunking ---
ENABLE_CHUNK_TYPING = True
CHUNK_SIZE_RANGE = (2, 7)
CHUNK_DELAY_RANGE = (0.08, 0.25)

# --- Предустановленные профили скорости для набора текста ---
TYPING_PROFILES = {
    "fast": {
        "KEY_PRESS_DELAY_RANGE": (0.01, 0.05),
        "KEY_DOWN_DURATION_RANGE": (0.008, 0.025),
        "MISTAKE_PROBABILITY": 0.01,
        "DOUBLE_CHAR_PROBABILITY": 0.005,
        "MISTAKE_CORRECTION_DELAY_RANGE": (0.05, 0.15),
        "BACKSPACE_DELAY_RANGE": (0.03, 0.08),
        "WORD_PAUSE_PROBABILITY": 0.05,
        "WORD_PAUSE_DURATION_RANGE": (0.05, 0.2),
        "LONG_PAUSE_PROBABILITY": 0.005,
        "LONG_PAUSE_DURATION_RANGE": (0.4, 1.0),
        "ENABLE_CHUNK_TYPING": True,
        "CHUNK_SIZE_RANGE": (4, 10),
        "CHUNK_DELAY_RANGE": (0.06, 0.15),
    },
    "medium": {
        "KEY_PRESS_DELAY_RANGE": (0.03, 0.11),
        "KEY_DOWN_DURATION_RANGE": (0.01, 0.04),
        "MISTAKE_PROBABILITY": 0.04,
        "DOUBLE_CHAR_PROBABILITY": 0.01,
        "MISTAKE_CORRECTION_DELAY_RANGE": (0.1, 0.4),
        "BACKSPACE_DELAY_RANGE": (0.05, 0.15),
        "WORD_PAUSE_PROBABILITY": 0.10,
        "WORD_PAUSE_DURATION_RANGE": (0.1, 0.5),
        "LONG_PAUSE_PROBABILITY": 0.01,
        "LONG_PAUSE_DURATION_RANGE": (0.8, 2.5),
        "ENABLE_CHUNK_TYPING": True,
        "CHUNK_SIZE_RANGE": (2, 7),
        "CHUNK_DELAY_RANGE": (0.08, 0.25),
    },
    "slow": {
        "KEY_PRESS_DELAY_RANGE": (0.08, 0.22),
        "KEY_DOWN_DURATION_RANGE": (0.04, 0.09),
        "MISTAKE_PROBABILITY": 0.08,
        "DOUBLE_CHAR_PROBABILITY": 0.02,
        "MISTAKE_CORRECTION_DELAY_RANGE": (0.3, 0.8),
        "BACKSPACE_DELAY_RANGE": (0.1, 0.3),
        "WORD_PAUSE_PROBABILITY": 0.18,
        "WORD_PAUSE_DURATION_RANGE": (0.4, 1.2),
        "LONG_PAUSE_PROBABILITY": 0.03,
        "LONG_PAUSE_DURATION_RANGE": (1.5, 4.0),
        "ENABLE_CHUNK_TYPING": False,
        "CHUNK_SIZE_RANGE": (1, 1),
        "CHUNK_DELAY_RANGE": (0.0, 0.0),
    },
    "paste": {
        "PASTE_DELAY_RANGE": (0.2, 0.6)
    }
}

NEIGHBORING_KEYS = {
    'q': 'wsa', 'w': 'qase', 'e': 'wsdr', 'r': 'edft', 't': 'rfgy', 'y': 'tghu', 'u': 'yhji',
    'i': 'ujko', 'o': 'iklp', 'p': 'ol', 'a': 'qwsz', 's': 'qwedcxza', 'd': 'werfvcxs',
    'f': 'ertgbvcd', 'g': 'rtyhnbvf', 'h': 'tyujmnbg', 'j': 'uikmnh', 'k': 'iolmj',
    'l': 'opk', 'z': 'asx', 'x': 'zsdc', 'c': 'xdfv', 'v': 'cfgb', 'b': 'vghn', 'n': 'bghjm', 'm': 'nhjk',
}
SHIFT_MAP = {
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
    '_': '-', '+': '=',
    '{': '[', '}': ']',
    '|': '\\', '?': '/',
    ':': ';', '"': "'",
    '<': ',', '>': '.',
}


# ==================== ASYNC РЕЖИМ ====================
if MODE == "async":
    # Импорт async human_like_mouse_click для integration
    from .mouse import human_like_mouse_click
    from .cdp_helpers import cdp_wait_for_visible

    async def _press_key_humanly(keyboard: Keyboard, key: str, duration_range: tuple):
        try:
            await keyboard.down(key)
            await asyncio.sleep(random.uniform(*duration_range))
            await keyboard.up(key)
        except Exception:
            # Fallback for unicode/accented chars (ô, é, ñ, ü, кириллица, etc.)
            # keyboard.down() only knows standard US keyboard keys
            await asyncio.sleep(random.uniform(*duration_range))
            await keyboard.insert_text(key)


    async def human_like_hotkey(keyboard, main_key, modifier="Control", down_delay=(0.02, 0.08), up_delay=(0.01, 0.06)):
        await keyboard.down(modifier)
        await asyncio.sleep(random.uniform(*down_delay))
        await keyboard.down(main_key)
        await asyncio.sleep(random.uniform(*down_delay))
        await keyboard.up(main_key)
        await asyncio.sleep(random.uniform(*up_delay))
        await keyboard.up(modifier)
        await asyncio.sleep(random.uniform(*up_delay))


    async def human_like_type(
            locator: Locator,
            text_to_type: str,
            speed_mode: Literal["fast", "medium", "slow", "manual", "paste"] = "paste",
            clear_before: bool = True,
            focus_with_click: bool = True
    ) -> bool:
        """
        Человекоподобный набор текста (ASYNC режим).

        Args:
            locator: Patchright/Playwright Locator
            text_to_type: Текст для набора
            speed_mode: "paste" (быстрая вставка) или "fast"/"medium"/"slow"/"manual" (посимвольный набор)
            clear_before: Очистить поле перед набором
            focus_with_click: Кликнуть на поле перед набором (иначе просто focus)

        Returns:
            True если успешно
        """
        page: Page = locator.page
        logger.info(f"[ASYNC] Typing '{text_to_type[:30]}...' into locator. Mode: {speed_mode}")

        modifier_key = "Meta" if IS_MAC else "Control"

        if speed_mode == "paste":
            try:
                await cdp_wait_for_visible(locator, timeout=10.0)
                if focus_with_click:
                    await locator.click()
                else:
                    await locator.focus()

                if clear_before:
                    await human_like_hotkey(page.keyboard, "A", modifier_key)
                    await asyncio.sleep(random.uniform(0.06, 0.15))
                    await _press_key_humanly(page.keyboard, "Backspace", (0.04, 0.12))
                    await asyncio.sleep(random.uniform(0.07, 0.15))

                logger.info("Simulating paste via insert_text (Huligan-compatible).")
                await asyncio.sleep(random.uniform(*TYPING_PROFILES["paste"]["PASTE_DELAY_RANGE"]))
                await page.keyboard.insert_text(text_to_type)
                logger.success("Successfully pasted text.")
                return True
            except Exception as e:
                logger.error(f"Error during paste operation: {e}")
                return False

        # Режимы fast/medium/slow/manual
        if speed_mode == "manual":
            current_params = {
                "KEY_PRESS_DELAY_RANGE": KEY_PRESS_DELAY_RANGE, "KEY_DOWN_DURATION_RANGE": KEY_DOWN_DURATION_RANGE,
                "MISTAKE_PROBABILITY": MISTAKE_PROBABILITY, "DOUBLE_CHAR_PROBABILITY": DOUBLE_CHAR_PROBABILITY,
                "MISTAKE_CORRECTION_DELAY_RANGE": MISTAKE_CORRECTION_DELAY_RANGE,
                "BACKSPACE_DELAY_RANGE": BACKSPACE_DELAY_RANGE,
                "WORD_PAUSE_PROBABILITY": WORD_PAUSE_PROBABILITY, "WORD_PAUSE_DURATION_RANGE": WORD_PAUSE_DURATION_RANGE,
                "LONG_PAUSE_PROBABILITY": LONG_PAUSE_PROBABILITY, "LONG_PAUSE_DURATION_RANGE": LONG_PAUSE_DURATION_RANGE,
                "ENABLE_CHUNK_TYPING": ENABLE_CHUNK_TYPING, "CHUNK_SIZE_RANGE": CHUNK_SIZE_RANGE,
                "CHUNK_DELAY_RANGE": CHUNK_DELAY_RANGE
            }
        elif speed_mode in TYPING_PROFILES:
            logger.debug(f"Using '{speed_mode}' typing profile.")
            current_params = TYPING_PROFILES[speed_mode]
        else:
            logger.warning(f"Unknown typing speed_mode '{speed_mode}'. Defaulting to 'medium'.")
            current_params = TYPING_PROFILES["medium"]

        p_key_delay = current_params["KEY_PRESS_DELAY_RANGE"]
        p_mistake_prob = current_params["MISTAKE_PROBABILITY"]
        p_mistake_delay = current_params["MISTAKE_CORRECTION_DELAY_RANGE"]
        p_double_char_prob = current_params["DOUBLE_CHAR_PROBABILITY"]
        p_key_down_duration = current_params["KEY_DOWN_DURATION_RANGE"]
        p_backspace_delay = current_params["BACKSPACE_DELAY_RANGE"]
        p_word_pause_prob = current_params["WORD_PAUSE_PROBABILITY"]
        p_word_pause_dur = current_params["WORD_PAUSE_DURATION_RANGE"]
        p_long_pause_prob = current_params["LONG_PAUSE_PROBABILITY"]
        p_long_pause_dur = current_params["LONG_PAUSE_DURATION_RANGE"]
        p_chunk_typing = current_params["ENABLE_CHUNK_TYPING"]
        p_chunk_size = current_params["CHUNK_SIZE_RANGE"]
        p_chunk_delay = current_params["CHUNK_DELAY_RANGE"]

        try:
            await cdp_wait_for_visible(locator, timeout=10.0)

            if focus_with_click:
                # Используем человекоподобный клик
                await human_like_mouse_click(locator, time_sleep=0.5, speed_mode="fast")
            else:
                await locator.focus()

            await asyncio.sleep(random.uniform(0.12, 0.20))

            if clear_before:
                keyboard = page.keyboard
                await human_like_hotkey(keyboard, "A", modifier_key)
                await asyncio.sleep(random.uniform(0.04, 0.12))
                await _press_key_humanly(keyboard, "Backspace", p_key_down_duration)
                await asyncio.sleep(random.uniform(0.1, 0.2))

            keyboard = page.keyboard
            text_len = len(text_to_type)
            cursor = 0
            while cursor < text_len:
                if p_chunk_typing:
                    chunk_size = random.randint(*p_chunk_size)
                    chunk = text_to_type[cursor: cursor + chunk_size]
                else:
                    chunk = text_to_type[cursor: cursor + 1]

                for char in chunk:

                    if random.random() < p_long_pause_prob:
                        await asyncio.sleep(random.uniform(*p_long_pause_dur))

                    if random.random() < p_mistake_prob and char.lower() in NEIGHBORING_KEYS:
                        mistake_char = random.choice(NEIGHBORING_KEYS[char.lower()])
                        logger.trace(f"Making a mistake: typed '{mistake_char}' instead of '{char}'")
                        await _press_key_humanly(keyboard, mistake_char, p_key_down_duration)
                        await asyncio.sleep(random.uniform(*p_mistake_delay))
                        await _press_key_humanly(keyboard, "Backspace", p_key_down_duration)
                        await asyncio.sleep(random.uniform(*p_backspace_delay))

                    is_upper = char.isupper()
                    needs_shift = char in SHIFT_MAP

                    if needs_shift or is_upper:
                        try:
                            await keyboard.press(char)
                        except Exception:
                            await keyboard.insert_text(char)
                    else:
                        await _press_key_humanly(keyboard, char, p_key_down_duration)

                    if random.random() < p_double_char_prob and char.isalpha():
                        logger.trace(f"Making a 'stuck key' mistake: typed '{char}' twice")
                        await _press_key_humanly(keyboard, char, p_key_down_duration)
                        await asyncio.sleep(random.uniform(*p_mistake_delay))
                        await _press_key_humanly(keyboard, "Backspace", p_key_down_duration)

                    await asyncio.sleep(random.uniform(*p_key_delay))
                    if char.isspace() and random.random() < p_word_pause_prob:
                        await asyncio.sleep(random.uniform(*p_word_pause_dur))

                cursor += len(chunk)
                if p_chunk_typing and cursor < text_len:
                    await asyncio.sleep(random.uniform(*p_chunk_delay))

            logger.success(f"Successfully typed text into the locator.")
            return True

        except Exception as e:
            logger.error(f"Global error in human_like_type: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False


# ==================== SYNC РЕЖИМ ====================
else:
    def _press_key_humanly(keyboard: Keyboard, key: str, duration_range: tuple):
        try:
            keyboard.down(key)
            time.sleep(random.uniform(*duration_range))
            keyboard.up(key)
        except Exception:
            # Fallback for unicode/accented chars (ô, é, ñ, ü, кириллица, etc.)
            time.sleep(random.uniform(*duration_range))
            keyboard.insert_text(key)


    def human_like_hotkey(keyboard, main_key, modifier="Control", down_delay=(0.02, 0.08), up_delay=(0.01, 0.06)):
        keyboard.down(modifier)
        time.sleep(random.uniform(*down_delay))
        keyboard.down(main_key)
        time.sleep(random.uniform(*down_delay))
        keyboard.up(main_key)
        time.sleep(random.uniform(*up_delay))
        keyboard.up(modifier)
        time.sleep(random.uniform(*up_delay))


    def human_like_type(
            locator: Locator,
            text_to_type: str,
            speed_mode: Literal["fast", "medium", "slow", "manual", "paste"] = "paste",
            clear_before: bool = True,
            focus_with_click: bool = True
    ) -> bool:
        """
        Человекоподобный набор текста (SYNC режим).

        Args:
            locator: Playwright Locator (sync API)
            text_to_type: Текст для набора
            speed_mode: "paste" (быстрая вставка) или "fast"/"medium"/"slow"/"manual" (посимвольный набор)
            clear_before: Очистить поле перед набором
            focus_with_click: Кликнуть на поле перед набором (иначе просто focus)

        Returns:
            True если успешно
        """
        # Импортируем mouse_random_click для sync режима
        from .mouse import human_like_mouse_click

        page: Page = locator.page
        logger.info(f"[SYNC] Typing '{text_to_type[:30]}...' into locator. Mode: {speed_mode}")

        modifier_key = "Meta" if IS_MAC else "Control"

        if speed_mode == "paste":
            try:
                locator.wait_for(state="visible", timeout=10000)
                if focus_with_click:
                    locator.click()
                else:
                    locator.focus()

                if clear_before:
                    human_like_hotkey(page.keyboard, "A", modifier_key)
                    time.sleep(random.uniform(0.06, 0.15))
                    _press_key_humanly(page.keyboard, "Backspace", (0.04, 0.12))
                    time.sleep(random.uniform(0.07, 0.15))

                logger.info("Simulating paste via insert_text (Huligan-compatible).")
                time.sleep(random.uniform(*TYPING_PROFILES["paste"]["PASTE_DELAY_RANGE"]))
                page.keyboard.insert_text(text_to_type)
                logger.success("Successfully pasted text.")
                return True
            except Exception as e:
                logger.error(f"Error during paste operation: {e}")
                return False

        # Режимы fast/medium/slow/manual
        if speed_mode == "manual":
            current_params = {
                "KEY_PRESS_DELAY_RANGE": KEY_PRESS_DELAY_RANGE, "KEY_DOWN_DURATION_RANGE": KEY_DOWN_DURATION_RANGE,
                "MISTAKE_PROBABILITY": MISTAKE_PROBABILITY, "DOUBLE_CHAR_PROBABILITY": DOUBLE_CHAR_PROBABILITY,
                "MISTAKE_CORRECTION_DELAY_RANGE": MISTAKE_CORRECTION_DELAY_RANGE,
                "BACKSPACE_DELAY_RANGE": BACKSPACE_DELAY_RANGE,
                "WORD_PAUSE_PROBABILITY": WORD_PAUSE_PROBABILITY, "WORD_PAUSE_DURATION_RANGE": WORD_PAUSE_DURATION_RANGE,
                "LONG_PAUSE_PROBABILITY": LONG_PAUSE_PROBABILITY, "LONG_PAUSE_DURATION_RANGE": LONG_PAUSE_DURATION_RANGE,
                "ENABLE_CHUNK_TYPING": ENABLE_CHUNK_TYPING, "CHUNK_SIZE_RANGE": CHUNK_SIZE_RANGE,
                "CHUNK_DELAY_RANGE": CHUNK_DELAY_RANGE
            }
        elif speed_mode in TYPING_PROFILES:
            logger.debug(f"Using '{speed_mode}' typing profile.")
            current_params = TYPING_PROFILES[speed_mode]
        else:
            logger.warning(f"Unknown typing speed_mode '{speed_mode}'. Defaulting to 'medium'.")
            current_params = TYPING_PROFILES["medium"]

        p_key_delay = current_params["KEY_PRESS_DELAY_RANGE"]
        p_mistake_prob = current_params["MISTAKE_PROBABILITY"]
        p_mistake_delay = current_params["MISTAKE_CORRECTION_DELAY_RANGE"]
        p_double_char_prob = current_params["DOUBLE_CHAR_PROBABILITY"]
        p_key_down_duration = current_params["KEY_DOWN_DURATION_RANGE"]
        p_backspace_delay = current_params["BACKSPACE_DELAY_RANGE"]
        p_word_pause_prob = current_params["WORD_PAUSE_PROBABILITY"]
        p_word_pause_dur = current_params["WORD_PAUSE_DURATION_RANGE"]
        p_long_pause_prob = current_params["LONG_PAUSE_PROBABILITY"]
        p_long_pause_dur = current_params["LONG_PAUSE_DURATION_RANGE"]
        p_chunk_typing = current_params["ENABLE_CHUNK_TYPING"]
        p_chunk_size = current_params["CHUNK_SIZE_RANGE"]
        p_chunk_delay = current_params["CHUNK_DELAY_RANGE"]

        try:
            locator.wait_for(state="visible", timeout=10000)

            if focus_with_click:
                human_like_mouse_click(locator)
            else:
                locator.focus()

            time.sleep(random.uniform(0.12, 0.20))

            if clear_before:
                keyboard = page.keyboard
                human_like_hotkey(keyboard, "A", modifier_key)
                time.sleep(random.uniform(0.04, 0.12))
                _press_key_humanly(keyboard, "Backspace", p_key_down_duration)
                time.sleep(random.uniform(0.1, 0.2))

            keyboard = page.keyboard
            text_len = len(text_to_type)
            cursor = 0
            while cursor < text_len:
                if p_chunk_typing:
                    chunk_size = random.randint(*p_chunk_size)
                    chunk = text_to_type[cursor: cursor + chunk_size]
                else:
                    chunk = text_to_type[cursor: cursor + 1]

                for char in chunk:

                    if random.random() < p_long_pause_prob:
                        time.sleep(random.uniform(*p_long_pause_dur))

                    if random.random() < p_mistake_prob and char.lower() in NEIGHBORING_KEYS:
                        mistake_char = random.choice(NEIGHBORING_KEYS[char.lower()])
                        logger.trace(f"Making a mistake: typed '{mistake_char}' instead of '{char}'")
                        _press_key_humanly(keyboard, mistake_char, p_key_down_duration)
                        time.sleep(random.uniform(*p_mistake_delay))
                        _press_key_humanly(keyboard, "Backspace", p_key_down_duration)
                        time.sleep(random.uniform(*p_backspace_delay))

                    is_upper = char.isupper()
                    needs_shift = char in SHIFT_MAP

                    if needs_shift or is_upper:
                        try:
                            keyboard.press(char)
                        except Exception:
                            keyboard.insert_text(char)
                    else:
                        _press_key_humanly(keyboard, char, p_key_down_duration)

                    if random.random() < p_double_char_prob and char.isalpha():
                        logger.trace(f"Making a 'stuck key' mistake: typed '{char}' twice")
                        _press_key_humanly(keyboard, char, p_key_down_duration)
                        time.sleep(random.uniform(*p_mistake_delay))
                        _press_key_humanly(keyboard, "Backspace", p_key_down_duration)

                    time.sleep(random.uniform(*p_key_delay))
                    if char.isspace() and random.random() < p_word_pause_prob:
                        time.sleep(random.uniform(*p_word_pause_dur))

                cursor += len(chunk)
                if p_chunk_typing and cursor < text_len:
                    time.sleep(random.uniform(*p_chunk_delay))

            logger.success(f"Successfully typed text into the locator.")
            return True

        except Exception as e:
            logger.error(f"Global error in human_like_type: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
