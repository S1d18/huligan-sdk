"""
Vision-LLM agent: locate elements on a page by natural-language description.

The flow is identical for every provider:

  1. Screenshot the page (PNG bytes).
  2. Base64-encode the image, paste it into a chat-completion request
     alongside the user's description and a strict JSON-only instruction.
  3. Parse the model's reply into ``{x, y, confidence}`` and dispatch a
     real input event (mouse click, type, hover) at those coords.

We use aiohttp instead of requests because the agent is awaited from
the same loop that drives Playwright; a blocking HTTP call would
freeze the browser session for the full LLM round-trip.

Output JSON contract (enforced via prompt, defensively re-parsed here):

    {"x": <int>, "y": <int>, "confidence": <float 0..1>}

``x == -1`` or ``confidence < threshold`` is treated as "not found",
which surfaces to the caller as ``locate() -> None`` and
``click()/fill()/hover() -> False``.
"""
import abc
import base64
import json
import os
import re
from typing import Any, Optional, Tuple

try:
    import aiohttp
except ImportError as e:
    raise ImportError(
        "aiohttp is required for huligan.vision. "
        "Install with: pip install huligan[vision]"
    ) from e


_PROVIDERS = ("openai", "anthropic")

_DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-latest",
}

_PROMPT_TEMPLATE = (
    "You are a precise UI-element locator. Given this screenshot of a "
    "web page, identify the pixel coordinates of the element described "
    "below.\n\n"
    "Element description: {description}\n\n"
    "Respond with ONLY a JSON object (no prose, no markdown fences) "
    "matching this exact schema:\n"
    '  {{"x": <int>, "y": <int>, "confidence": <float between 0.0 and 1.0>}}\n\n'
    "x and y are pixel coordinates measured from the top-left corner of "
    "the screenshot, pointing at the visual centre of the element. "
    "If you cannot find the element with reasonable certainty, return "
    '{{"x": -1, "y": -1, "confidence": 0.0}}.'
)


class VisionAgentError(Exception):
    """Raised when the LLM call fails or returns an unparseable payload."""


# ---------------------------------------------------------------------------
# Provider backends
# ---------------------------------------------------------------------------


class BaseProvider(abc.ABC):
    """
    Abstract provider. Subclasses talk to one vision-LLM REST API.

    The shared ``locate()`` entry point builds the prompt + base64 image
    payload and dispatches to the provider-specific ``_request`` hook,
    which must return the raw assistant text. JSON parsing is shared.
    """

    name: str = ""

    def __init__(
        self,
        api_key: str,
        *,
        model: Optional[str] = None,
        timeout: int = 60,
        base_url: Optional[str] = None,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.model = model or _DEFAULT_MODELS[self.name]
        self.timeout = timeout
        self.base_url = base_url

    @abc.abstractmethod
    async def _request(self, image_b64: str, description: str) -> str:
        """POST to the provider; return the assistant's raw text reply."""

    async def locate(self, image_bytes: bytes, description: str) -> dict:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        raw = await self._request(b64, description)
        return _parse_json_reply(raw)


class OpenAIProvider(BaseProvider):
    name = "openai"
    _DEFAULT_URL = "https://api.openai.com/v1/chat/completions"

    async def _request(self, image_b64: str, description: str) -> str:
        url = self.base_url or self._DEFAULT_URL
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": _PROMPT_TEMPLATE.format(description=description),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}",
                            },
                        },
                    ],
                }
            ],
            # Low temperature: locating a button is a deterministic task,
            # not a creative one. response_format pins JSON when supported.
            "temperature": 0.0,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=body) as resp:
                data = await resp.json(content_type=None)
        if "error" in data:
            raise VisionAgentError(f"openai error: {data['error']}")
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise VisionAgentError(f"openai: malformed response: {data}") from e


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    _DEFAULT_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    async def _request(self, image_b64: str, description: str) -> str:
        url = self.base_url or self._DEFAULT_URL
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self._API_VERSION,
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": 256,
            "temperature": 0.0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": _PROMPT_TEMPLATE.format(description=description),
                        },
                    ],
                }
            ],
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=body) as resp:
                data = await resp.json(content_type=None)
        if data.get("type") == "error" or "error" in data:
            raise VisionAgentError(f"anthropic error: {data.get('error', data)}")
        try:
            # Anthropic returns a list of content blocks; take the first text one.
            for block in data["content"]:
                if block.get("type") == "text":
                    return block["text"]
            raise VisionAgentError(f"anthropic: no text block in response: {data}")
        except (KeyError, TypeError) as e:
            raise VisionAgentError(f"anthropic: malformed response: {data}") from e


def _build_provider(
    provider: str,
    api_key: str,
    model: Optional[str],
    timeout: int,
    base_url: Optional[str],
) -> BaseProvider:
    if provider == "openai":
        return OpenAIProvider(api_key, model=model, timeout=timeout, base_url=base_url)
    if provider == "anthropic":
        return AnthropicProvider(
            api_key, model=model, timeout=timeout, base_url=base_url
        )
    raise ValueError(
        f"Unknown vision provider: {provider!r}. "
        f"Supported: {', '.join(_PROVIDERS)}"
    )


# ---------------------------------------------------------------------------
# JSON-reply parsing
# ---------------------------------------------------------------------------


_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _parse_json_reply(text: str) -> dict:
    """
    Extract ``{x, y, confidence}`` from the model's reply.

    OpenAI's ``response_format=json_object`` makes this trivial, but
    Anthropic and older OpenAI vision models occasionally wrap the
    payload in prose or markdown fences — fall back to a regex search
    for the first ``{...}`` block before raising.
    """
    text = text.strip()
    candidates = [text]
    # Strip markdown code fences if the model wrapped the JSON.
    if text.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        candidates.append(stripped.strip())
    # Last-ditch: first {...} block anywhere in the reply.
    m = _JSON_OBJECT_RE.search(text)
    if m:
        candidates.append(m.group(0))

    for c in candidates:
        try:
            data = json.loads(c)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        try:
            x = int(data["x"])
            y = int(data["y"])
            confidence = float(data.get("confidence", 0.0))
        except (KeyError, ValueError, TypeError):
            continue
        return {"x": x, "y": y, "confidence": confidence}

    raise VisionAgentError(f"Could not parse JSON from model reply: {text!r}")


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------


class VisionAgent:
    """
    Async vision-LLM agent for clicking elements by natural-language description.

    Args:
        provider: ``"openai"`` or ``"anthropic"``.
        api_key:  Provider API key.
        model:    Override the per-provider default (``gpt-4o`` /
                  ``claude-3-5-sonnet-latest``).
        confidence_threshold: Minimum LLM confidence to treat a hit as
                  valid. Below this, ``locate()`` returns ``None`` and
                  the action methods return ``False``. Default ``0.5``.
        timeout:  Per-request HTTP timeout in seconds. Default ``60``.
        base_url: Override the provider endpoint (proxies, Azure, etc.).

    The methods all take a Playwright ``page`` and run a single
    screenshot → LLM → action round-trip. Note: ``page.evaluate()`` is
    blocked by huligan's CDP stealth patches, so we deliberately route
    every action through low-level input primitives
    (``page.mouse.click``, ``page.keyboard.type``, ``page.mouse.move``).
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        *,
        model: Optional[str] = None,
        confidence_threshold: float = 0.5,
        timeout: int = 60,
        base_url: Optional[str] = None,
    ):
        if provider not in _PROVIDERS:
            raise ValueError(
                f"Unknown vision provider: {provider!r}. "
                f"Supported: {', '.join(_PROVIDERS)}"
            )
        self.provider = provider
        self.api_key = api_key
        self.model = model or _DEFAULT_MODELS[provider]
        self.confidence_threshold = confidence_threshold
        self.timeout = timeout
        self.base_url = base_url
        self._backend = _build_provider(provider, api_key, self.model, timeout, base_url)

    @classmethod
    def from_env(cls, **overrides: Any) -> "VisionAgent":
        """
        Build an agent from env vars. Keyword overrides win.

            HULIGAN_VISION_PROVIDER   one of "openai" / "anthropic"
            HULIGAN_VISION_API_KEY    provider API key
            HULIGAN_VISION_MODEL      optional model override
        """
        provider = overrides.pop("provider", None) or os.environ.get(
            "HULIGAN_VISION_PROVIDER"
        )
        api_key = overrides.pop("api_key", None) or os.environ.get(
            "HULIGAN_VISION_API_KEY"
        )
        model = overrides.pop("model", None) or os.environ.get("HULIGAN_VISION_MODEL")
        if not provider:
            raise ValueError(
                "Set HULIGAN_VISION_PROVIDER or pass provider= explicitly."
            )
        if not api_key:
            raise ValueError(
                "Set HULIGAN_VISION_API_KEY or pass api_key= explicitly."
            )
        return cls(provider=provider, api_key=api_key, model=model, **overrides)

    # -----------------------------------------------------------------
    # Core: screenshot → LLM → coords
    # -----------------------------------------------------------------

    async def locate(
        self,
        page: Any,
        description: str,
        *,
        confidence_threshold: Optional[float] = None,
    ) -> Optional[Tuple[int, int]]:
        """
        Return ``(x, y)`` pixel coordinates for the described element,
        or ``None`` if the model's confidence is below the threshold
        or it reported "not found".
        """
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self.confidence_threshold
        )
        image_bytes = await page.screenshot(type="png")
        result = await self._backend.locate(image_bytes, description)
        if result["x"] < 0 or result["y"] < 0:
            return None
        if result["confidence"] < threshold:
            return None
        return (result["x"], result["y"])

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------

    async def click(
        self,
        page: Any,
        description: str,
        *,
        button: str = "left",
        click_count: int = 1,
        confidence_threshold: Optional[float] = None,
    ) -> bool:
        coords = await self.locate(
            page, description, confidence_threshold=confidence_threshold
        )
        if coords is None:
            return False
        x, y = coords
        await page.mouse.click(x, y, button=button, click_count=click_count)
        return True

    async def double_click(
        self,
        page: Any,
        description: str,
        *,
        confidence_threshold: Optional[float] = None,
    ) -> bool:
        return await self.click(
            page,
            description,
            click_count=2,
            confidence_threshold=confidence_threshold,
        )

    async def fill(
        self,
        page: Any,
        description: str,
        text: str,
        *,
        confidence_threshold: Optional[float] = None,
        type_delay_ms: int = 50,
    ) -> bool:
        coords = await self.locate(
            page, description, confidence_threshold=confidence_threshold
        )
        if coords is None:
            return False
        x, y = coords
        # Click focuses the input; keyboard.type then dispatches real
        # keydown/keypress/keyup so behavioural-signal detectors see a
        # typing rhythm rather than a single .value assignment.
        await page.mouse.click(x, y)
        await page.keyboard.type(text, delay=type_delay_ms)
        return True

    async def hover(
        self,
        page: Any,
        description: str,
        *,
        confidence_threshold: Optional[float] = None,
    ) -> bool:
        coords = await self.locate(
            page, description, confidence_threshold=confidence_threshold
        )
        if coords is None:
            return False
        x, y = coords
        await page.mouse.move(x, y)
        return True
