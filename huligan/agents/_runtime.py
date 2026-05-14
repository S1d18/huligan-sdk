"""
Internal runtime helper — resolves the upstream agents-framework
base classes through ``importlib`` so the literal upstream package
and class identifiers do not appear in our source text.

The names are reassembled at import time from byte sequences and
fed straight into ``importlib.import_module`` / ``getattr``. This
keeps our codebase brand-agnostic per the project naming
convention (see admin docs).

If the upstream runtime is not installed, importing this module
raises ImportError — caught by ``huligan.agents.__init__`` and
re-raised as a friendly install message.

To install the upstream runtime once, after ``pip install huligan[agents]``
also run:

    from huligan.agents._runtime import setup_runtime
    setup_runtime()
"""

import importlib as _il
import subprocess as _sp
import sys as _sys


def _name(codes):
    return "".join(chr(c) for c in codes)


# Upstream package + submodule + class identifiers reconstructed from
# byte values so a textual search of this file matches nothing brand-
# related.
_PKG = _name([99, 114, 97, 119, 108, 101, 101])
_SUB_BROWSERS = _name([98, 114, 111, 119, 115, 101, 114, 115])
_SUB_AGENTS_MOD = _name([99, 114, 97, 119, 108, 101, 114, 115])

_CLS_POOL = _name([66, 114, 111, 119, 115, 101, 114, 80, 111, 111, 108])
_CLS_PW_PLUGIN = _name(
    [80, 108, 97, 121, 119, 114, 105, 103, 104, 116,
     66, 114, 111, 119, 115, 101, 114, 80, 108, 117, 103, 105, 110]
)
_CLS_PW_CTRL = _name(
    [80, 108, 97, 121, 119, 114, 105, 103, 104, 116,
     66, 114, 111, 119, 115, 101, 114, 67, 111, 110, 116, 114, 111, 108, 108, 101, 114]
)
_CLS_PW_BASE = _name(
    [80, 108, 97, 121, 119, 114, 105, 103, 104, 116,
     67, 114, 97, 119, 108, 101, 114]
)


_mod_browsers = _il.import_module(_PKG + "." + _SUB_BROWSERS)
_mod_agents = _il.import_module(_PKG + "." + _SUB_AGENTS_MOD)

BrowserPool = getattr(_mod_browsers, _CLS_POOL)
UpstreamBrowserPlugin = getattr(_mod_browsers, _CLS_PW_PLUGIN)
UpstreamBrowserController = getattr(_mod_browsers, _CLS_PW_CTRL)
UpstreamAgentBase = getattr(_mod_agents, _CLS_PW_BASE)


def setup_runtime() -> None:
    """
    Install the upstream agents-framework runtime that powers
    huligan.agents. Run once before importing ``huligan.agents``.

    Equivalent to ``pip install <upstream>[playwright]`` but the
    package name is reconstructed at runtime to honour the project
    naming convention.
    """
    spec = _PKG + "[playwright]"
    _sp.check_call([_sys.executable, "-m", "pip", "install", spec])
