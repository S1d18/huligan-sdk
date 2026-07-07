"""
Huligan SDK — MCP server: drive the antidetect browser as LLM tools.

Two ways to run this for real, not shown by this script:

    python -m huligan.mcp                    # stdio MCP server (Claude Desktop etc.)

    from huligan import run_mcp_server       # embed it yourself
    run_mcp_server()

See docs/MCP_SERVER.md for the Claude Desktop config recipe and the
full tool reference (huligan_open_session, huligan_goto,
huligan_vision_click, huligan_extract_markdown, huligan_close_session).

This script instead calls the same five tool functions directly,
in-process, so you can see what an MCP host would actually invoke and
sanity-check the server without wiring up a real MCP client first.

Requires the mcp extra, plus markdown for the extract step below:

    pip install "huligan[mcp,markdown]"
"""
import asyncio

from huligan.mcp.server import (
    huligan_open_session,
    huligan_goto,
    huligan_extract_markdown,
    huligan_close_session,
)


async def main():
    session_id = "example-session"

    print(await huligan_open_session(session_id, proxy=None, headless=True))

    print(await huligan_goto(
        session_id,
        "https://en.wikipedia.org/wiki/Web_scraping",
        wait_until="domcontentloaded",
    ))

    md = await huligan_extract_markdown(session_id)
    print(f"Markdown length: {len(md)} chars")
    print("-" * 60)
    print(md[:1000])
    print("-" * 60)

    print(await huligan_close_session(session_id))


if __name__ == "__main__":
    asyncio.run(main())
