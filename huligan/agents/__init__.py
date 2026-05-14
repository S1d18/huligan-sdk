"""
huligan.agents — agent / scraping integration for the Huligan
antidetect browser.

Lets you run a high-level scraping framework on top of huligan's
patched Chromium, so the same browser that drives manual antidetect
work also powers headless scraping pipelines and LLM browser agents.

The upstream agents-framework runtime is loaded dynamically — it is
NOT a hard pip dependency of this package. To install it, run:

    pip install huligan[agents]
    python -c "from huligan.agents._runtime import setup_runtime; setup_runtime()"

The second step installs the upstream runtime under the hood.

Public surface:

    HuliganBrowserPlugin     — plugin class that boots Huligan Chrome
                              with our .conf fingerprint, proxy
                              forwarder, and GeoIP pre-resolved.
    HuliganBrowserController — controller wrapper that owns the
                              underlying huligan Browser so cleanup
                              tears down the Chrome subprocess.
    HuliganAgent             — preconfigured agent that wires the
                              plugin into a browser pool.

If the upstream runtime is missing, importing any of the public
classes raises a clear ImportError pointing the user at the
``setup_runtime()`` call above.
"""

try:
    from .plugin import HuliganBrowserPlugin, HuliganBrowserController
    from .agent import HuliganAgent
    _AVAILABLE = True
except ImportError as e:
    _AVAILABLE = False
    _IMPORT_ERROR = e

    def _missing(*args, **kwargs):
        raise ImportError(
            "huligan.agents requires the upstream agents-framework "
            "runtime. Install with:\n"
            "    pip install huligan[agents]\n"
            "    python -c \"from huligan.agents._runtime import "
            "setup_runtime; setup_runtime()\"\n"
            f"Original error: {_IMPORT_ERROR}"
        )

    HuliganBrowserPlugin = _missing       # type: ignore
    HuliganBrowserController = _missing   # type: ignore
    HuliganAgent = _missing               # type: ignore


__all__ = ["HuliganBrowserPlugin", "HuliganBrowserController", "HuliganAgent"]
