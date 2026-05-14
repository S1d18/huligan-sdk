"""
huligan.vision — vision-LLM agent for clicking elements by description.

Provides a single ``VisionAgent`` facade over OpenAI (gpt-4o family)
and Anthropic (claude-3.5-sonnet) vision models. The agent takes a
screenshot of the current page, asks the model for pixel coordinates
of the described element, then dispatches a real input event at those
coords through Playwright's low-level mouse/keyboard primitives.

The action surface is deliberately CDP-stealth-safe: every method
routes through ``page.mouse.*`` / ``page.keyboard.*`` /
``page.screenshot()`` — no ``page.evaluate()`` calls, which are
blocked by huligan's paranoid mode.

Optional dependency — install via:

    pip install huligan[vision]

Public surface:

    VisionAgent(provider, api_key, *, model=None,
                confidence_threshold=0.5, timeout=60, base_url=None)
        Facade. ``provider`` is one of ``"openai"`` or ``"anthropic"``.
        Use ``from_env()`` to read ``HULIGAN_VISION_PROVIDER``,
        ``HULIGAN_VISION_API_KEY``, ``HULIGAN_VISION_MODEL`` instead.

    VisionAgentError
        Raised on HTTP errors, malformed responses, and unparseable
        model replies.

The constructor is the import boundary — if ``aiohttp`` is missing, it
raises ImportError pointing at ``pip install huligan[vision]``.
"""

try:
    from .agent import (
        VisionAgent,
        VisionAgentError,
        BaseProvider,
        OpenAIProvider,
        AnthropicProvider,
    )
    _AVAILABLE = True
except ImportError as e:
    _AVAILABLE = False
    _IMPORT_ERROR = e

    def _missing(*args, **kwargs):
        raise ImportError(
            "huligan.vision requires the vision extra. "
            "Install with: pip install huligan[vision]\n"
            f"Original error: {_IMPORT_ERROR}"
        )

    VisionAgent = _missing          # type: ignore
    VisionAgentError = _missing     # type: ignore
    BaseProvider = _missing         # type: ignore
    OpenAIProvider = _missing       # type: ignore
    AnthropicProvider = _missing    # type: ignore


__all__ = [
    "VisionAgent",
    "VisionAgentError",
    "BaseProvider",
    "OpenAIProvider",
    "AnthropicProvider",
]
