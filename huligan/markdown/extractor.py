"""
HTML-to-Markdown extraction with readability filtering.

trafilatura is the primary engine — it strips boilerplate (nav,
ads, footers, cookie banners) and emits a content-only document.
markdownify is the fallback: a verbatim HTML-to-Markdown converter
used when trafilatura returns nothing useful (SPA shells, very
small docs, JSON-rendered pages).

We intentionally keep this module sync-only at the conversion
level — the only async surface is ``extract_markdown(page)``,
which simply awaits ``page.content()`` and forwards to the sync
converter. Conversion is CPU-bound and fast; no need for threads.
"""
from typing import Literal, Optional

try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

try:
    from markdownify import markdownify as _md
    _HAS_MARKDOWNIFY = True
except ImportError:
    _HAS_MARKDOWNIFY = False


if not (_HAS_TRAFILATURA or _HAS_MARKDOWNIFY):
    # Surface this at import time so __init__.py can swap in the
    # _missing stubs and direct the user to `pip install huligan[markdown]`.
    raise ImportError(
        "Neither trafilatura nor markdownify is installed. "
        "Install with: pip install huligan[markdown]"
    )


Strategy = Literal["auto", "trafilatura", "markdownify"]


class MarkdownExtractor:
    """
    Convert HTML to Markdown with readability filtering.

    Args:
        strategy: ``"auto"`` (trafilatura with markdownify fallback,
            default), ``"trafilatura"`` (boilerplate-stripped, fail
            if empty), or ``"markdownify"`` (verbatim conversion).
        include_links: Keep ``<a href>`` as Markdown links.
        include_images: Keep ``<img>`` as Markdown image tags.
            Off by default — images are usually noise for LLMs.
        min_text_length: If the trafilatura result is shorter than
            this, ``"auto"`` falls back to markdownify. Has no
            effect when ``strategy`` is locked to a single engine.
    """

    def __init__(
        self,
        strategy: Strategy = "auto",
        include_links: bool = True,
        include_images: bool = False,
        min_text_length: int = 100,
    ):
        self.strategy = strategy
        self.include_links = include_links
        self.include_images = include_images
        self.min_text_length = min_text_length

    def from_html(self, html: str, base_url: Optional[str] = None) -> str:
        """
        Convert an HTML string to Markdown.

        ``base_url`` is forwarded to trafilatura so relative links
        get resolved against the page origin. markdownify doesn't
        accept it — relative hrefs stay relative there.
        """
        if not html:
            return ""

        if self.strategy == "trafilatura":
            return self._run_trafilatura(html, base_url) or ""

        if self.strategy == "markdownify":
            return self._run_markdownify(html)

        # auto: trafilatura first, fall back if the result is empty
        # or too short to be useful (likely SPA shell / JSON page).
        if _HAS_TRAFILATURA:
            result = self._run_trafilatura(html, base_url)
            if result and len(result.strip()) >= self.min_text_length:
                return result
        return self._run_markdownify(html)

    def _run_trafilatura(self, html: str, base_url: Optional[str]) -> str:
        if not _HAS_TRAFILATURA:
            return ""
        result = trafilatura.extract(
            html,
            url=base_url,
            output_format="markdown",
            include_links=self.include_links,
            include_images=self.include_images,
            include_tables=True,
            include_comments=False,
            favor_precision=False,
        )
        return result or ""

    def _run_markdownify(self, html: str) -> str:
        if not _HAS_MARKDOWNIFY:
            return ""
        # Strip <a>/<img> tags entirely when the user disables them
        # — markdownify doesn't have a flag for that, but listing a
        # tag in `strip` drops both opening and closing forms.
        strip = []
        if not self.include_links:
            strip.append("a")
        if not self.include_images:
            strip.append("img")
        return _md(html, strip=strip or None, heading_style="ATX").strip()


async def extract_markdown(
    page,
    strategy: Strategy = "auto",
    include_links: bool = True,
    include_images: bool = False,
    min_text_length: int = 100,
) -> str:
    """
    Pull HTML from a live Playwright Page and return Markdown.

    Uses ``page.content()`` (works under paranoid mode, unlike
    ``page.evaluate()``) and ``page.url`` for link resolution.
    """
    html = await page.content()
    base_url = getattr(page, "url", None)
    extractor = MarkdownExtractor(
        strategy=strategy,
        include_links=include_links,
        include_images=include_images,
        min_text_length=min_text_length,
    )
    return extractor.from_html(html, base_url=base_url)
