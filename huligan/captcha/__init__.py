"""
huligan.captcha — async wrappers around third-party CAPTCHA solver APIs.

Provides a single ``CaptchaSolver`` facade over 2Captcha, AntiCaptcha
and CapSolver. Each ``solve_X()`` returns the solver token as a
string; injecting that token into the page is the caller's job
(see ``examples/example_captcha.py`` for the standard flow).

Optional dependency — install via:

    pip install huligan[captcha]

Public surface:

    CaptchaSolver(provider, api_key, *, timeout=120, poll_interval=5)
        Facade. ``provider`` is one of ``"2captcha"``, ``"anticaptcha"``,
        ``"capsolver"``. Use ``from_env()`` to read ``HULIGAN_CAPTCHA_PROVIDER``
        and ``HULIGAN_CAPTCHA_API_KEY`` instead.

    CaptchaSolveError
        Raised on solver timeouts, unknown errors, malformed responses,
        and explicit provider error codes (ERROR_KEY, ERROR_ZERO_BALANCE, etc.).

The constructor is the import boundary — if ``aiohttp`` is missing, it
raises ImportError pointing at ``pip install huligan[captcha]``.
"""

try:
    from .solvers import (
        CaptchaSolver,
        CaptchaSolveError,
        BaseSolver,
        TwoCaptchaSolver,
        AntiCaptchaSolver,
        CapSolverSolver,
    )
    _AVAILABLE = True
except ImportError as e:
    _AVAILABLE = False
    _IMPORT_ERROR = e

    def _missing(*args, **kwargs):
        raise ImportError(
            "huligan.captcha requires the captcha extra. "
            "Install with: pip install huligan[captcha]\n"
            f"Original error: {_IMPORT_ERROR}"
        )

    CaptchaSolver = _missing            # type: ignore
    CaptchaSolveError = _missing        # type: ignore
    BaseSolver = _missing               # type: ignore
    TwoCaptchaSolver = _missing         # type: ignore
    AntiCaptchaSolver = _missing        # type: ignore
    CapSolverSolver = _missing          # type: ignore


__all__ = [
    "CaptchaSolver",
    "CaptchaSolveError",
    "BaseSolver",
    "TwoCaptchaSolver",
    "AntiCaptchaSolver",
    "CapSolverSolver",
]
