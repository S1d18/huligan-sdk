"""
huligan.mcp — Model Context Protocol server exposing the Huligan
antidetect browser as MCP tools.

Run as a stdio MCP server:

    python -m huligan.mcp

Then point an MCP client (Claude Desktop, etc.) at it. See
``huligan-sdk/docs/MCP_SERVER.md`` for the full integration recipe.

Optional dependency — install via:

    pip install huligan[mcp]

Public surface intentionally minimal:

    huligan_open_session(session_id, proxy=None, headless=False)
    huligan_goto(session_id, url, wait_until="domcontentloaded")
    huligan_vision_click(session_id, description)   # huligan[vision]
    huligan_extract_markdown(session_id)            # huligan[markdown]
    huligan_close_session(session_id)
"""

try:
    from .server import mcp, run  # noqa: F401
    _AVAILABLE = True
except ImportError as _e:
    _AVAILABLE = False
    _IMPORT_ERROR = _e

    def run(*args, **kwargs):  # type: ignore[misc]
        raise ImportError(
            "huligan.mcp requires the mcp extra. "
            "Install with: pip install huligan[mcp]\n"
            f"Original error: {_IMPORT_ERROR}"
        )

__all__ = ["run"]
