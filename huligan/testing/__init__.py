"""Testing / diagnostics helpers for Huligan (auxiliary, not authoritative).

The detection sweep is an AUXILIARY signal: every rung reads a live third-party
detector over CDP, which this project has repeatedly seen return a stale/frozen
snapshot (a false "100%"). An operator's visual read of the headed window is the
authority. Keep sweep runs manual/headed; never gate CI on them.
"""
from .detection_sweep import (
    ALLOWLIST,
    Adapter,
    SiteVerdict,
    apply_allowlist,
    render_summary,
    run_sweep,
    to_json,
)

__all__ = [
    "SiteVerdict",
    "Adapter",
    "ALLOWLIST",
    "run_sweep",
    "apply_allowlist",
    "render_summary",
    "to_json",
]
