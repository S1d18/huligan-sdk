"""
huligan.markdown — HTML-to-Markdown extraction for LLM agents.

Turns a live Playwright Page (or a raw HTML string) into clean
Markdown suitable for feeding into an LLM. Primary engine is
trafilatura (readability + boilerplate removal); markdownify is
used as a fallback when trafilatura cannot find a main content
block (e.g. SPA shells, JSON-rendered pages, or very small docs).

Optional dependency — install via:

    pip install huligan[markdown]

Public surface:

    extract_markdown(page, **opts) -> str
        Async helper. Calls page.content() + page.url and runs the
        extractor. Designed to play nicely with paranoid mode where
        page.evaluate() is blocked — we only need page.content().

    MarkdownExtractor(strategy="auto", include_links=True,
                      include_images=False, min_text_length=100)
        Reusable extractor. Use ``from_html(html, base_url=...)``
        when you already have the HTML in hand.

If neither trafilatura nor markdownify is installed, importing the
public names raises a clear ImportError pointing the user at
`pip install huligan[markdown]`.
"""

try:
    from .extractor import extract_markdown, MarkdownExtractor
    _AVAILABLE = True
except ImportError as e:
    _AVAILABLE = False
    _IMPORT_ERROR = e

    def _missing(*args, **kwargs):
        raise ImportError(
            "huligan.markdown requires the markdown extra. "
            "Install with: pip install huligan[markdown]\n"
            f"Original error: {_IMPORT_ERROR}"
        )

    extract_markdown = _missing      # type: ignore
    MarkdownExtractor = _missing     # type: ignore


__all__ = ["extract_markdown", "MarkdownExtractor"]
