"""
Async CAPTCHA solver clients (2Captcha, AntiCaptcha, CapSolver).

Each provider has its own request/response shape but the lifecycle
is identical: POST a task, then poll until ready or timed out. The
shared loop lives on ``BaseSolver._poll``; subclasses implement two
hooks — ``_create_task`` (returns an opaque task id) and
``_get_result`` (returns the token string, or ``None`` if not ready).

We use aiohttp instead of requests because solve_X() is awaited from
the same loop that drives Playwright; a blocking HTTP call would
freeze the browser session for the full poll duration (often 30s+).
"""
import abc
import asyncio
import base64
import os
from typing import Any, Optional

try:
    import aiohttp
except ImportError as e:
    raise ImportError(
        "aiohttp is required for huligan.captcha. "
        "Install with: pip install huligan[captcha]"
    ) from e


_PROVIDERS = ("2captcha", "anticaptcha", "capsolver")


class CaptchaSolveError(Exception):
    """Raised when a solver times out, errors, or returns an unexpected payload."""


class BaseSolver(abc.ABC):
    """
    Abstract base. Subclasses talk to one provider's REST API.

    The ``solve_*`` methods on the public ``CaptchaSolver`` facade
    forward to ``_create_task`` + ``_poll`` here so the polling loop
    (timeout, interval, cancellation) lives in one place.
    """

    def __init__(self, api_key: str, *, timeout: int = 120, poll_interval: int = 5):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.timeout = timeout
        self.poll_interval = poll_interval

    @abc.abstractmethod
    async def _create_task(self, session: aiohttp.ClientSession, payload: dict) -> str:
        """POST the task to the provider; return the provider's task id."""

    @abc.abstractmethod
    async def _get_result(
        self, session: aiohttp.ClientSession, task_id: str
    ) -> Optional[str]:
        """Poll once. Return the token string if ready, else None."""

    @abc.abstractmethod
    async def get_balance(self) -> float:
        """Return the account balance in USD (or provider's native currency)."""

    async def _poll(
        self,
        session: aiohttp.ClientSession,
        task_id: str,
        timeout: Optional[int],
        poll_interval: Optional[int],
    ) -> str:
        deadline = asyncio.get_event_loop().time() + (timeout or self.timeout)
        interval = poll_interval or self.poll_interval
        # First-poll delay matches the providers' own guidance: tasks
        # are essentially never ready in under ~5s, so we don't hammer
        # res.php / getTaskResult before that.
        await asyncio.sleep(interval)
        while True:
            token = await self._get_result(session, task_id)
            if token is not None:
                return token
            if asyncio.get_event_loop().time() >= deadline:
                raise CaptchaSolveError(
                    f"Solver timed out after {timeout or self.timeout}s "
                    f"(task_id={task_id})"
                )
            await asyncio.sleep(interval)

    async def _run(
        self,
        payload: dict,
        timeout: Optional[int],
        poll_interval: Optional[int],
    ) -> str:
        async with aiohttp.ClientSession() as session:
            task_id = await self._create_task(session, payload)
            return await self._poll(session, task_id, timeout, poll_interval)


# ---------------------------------------------------------------------------
# 2Captcha
# ---------------------------------------------------------------------------


class TwoCaptchaSolver(BaseSolver):
    _IN_URL = "https://2captcha.com/in.php"
    _RES_URL = "https://2captcha.com/res.php"

    async def _create_task(self, session: aiohttp.ClientSession, payload: dict) -> str:
        data = {"key": self.api_key, "json": "1", **payload}
        async with session.post(self._IN_URL, data=data) as resp:
            body = await resp.json(content_type=None)
        if body.get("status") != 1:
            raise CaptchaSolveError(f"2captcha create failed: {body.get('request')}")
        return str(body["request"])

    async def _get_result(
        self, session: aiohttp.ClientSession, task_id: str
    ) -> Optional[str]:
        params = {
            "key": self.api_key,
            "action": "get",
            "id": task_id,
            "json": "1",
        }
        async with session.get(self._RES_URL, params=params) as resp:
            body = await resp.json(content_type=None)
        if body.get("status") == 1:
            return str(body["request"])
        msg = str(body.get("request", ""))
        if msg == "CAPCHA_NOT_READY":
            return None
        raise CaptchaSolveError(f"2captcha error: {msg}")

    async def get_balance(self) -> float:
        params = {"key": self.api_key, "action": "getbalance", "json": "1"}
        async with aiohttp.ClientSession() as session:
            async with session.get(self._RES_URL, params=params) as resp:
                body = await resp.json(content_type=None)
        if body.get("status") != 1:
            raise CaptchaSolveError(f"2captcha balance error: {body.get('request')}")
        return float(body["request"])


# ---------------------------------------------------------------------------
# AntiCaptcha
# ---------------------------------------------------------------------------


class AntiCaptchaSolver(BaseSolver):
    _CREATE_URL = "https://api.anti-captcha.com/createTask"
    _RESULT_URL = "https://api.anti-captcha.com/getTaskResult"
    _BALANCE_URL = "https://api.anti-captcha.com/getBalance"

    async def _create_task(self, session: aiohttp.ClientSession, payload: dict) -> str:
        body = {"clientKey": self.api_key, "task": payload}
        async with session.post(self._CREATE_URL, json=body) as resp:
            data = await resp.json(content_type=None)
        if data.get("errorId"):
            raise CaptchaSolveError(
                f"anticaptcha create failed: {data.get('errorCode')} "
                f"{data.get('errorDescription')}"
            )
        return str(data["taskId"])

    async def _get_result(
        self, session: aiohttp.ClientSession, task_id: str
    ) -> Optional[str]:
        body = {"clientKey": self.api_key, "taskId": int(task_id)}
        async with session.post(self._RESULT_URL, json=body) as resp:
            data = await resp.json(content_type=None)
        if data.get("errorId"):
            raise CaptchaSolveError(
                f"anticaptcha error: {data.get('errorCode')} "
                f"{data.get('errorDescription')}"
            )
        if data.get("status") == "processing":
            return None
        if data.get("status") == "ready":
            sol = data.get("solution", {})
            # Different task types return the token under different keys.
            # gRecaptchaResponse for reCAPTCHA, token for Turnstile/hCaptcha,
            # text for image CAPTCHAs.
            for key in ("gRecaptchaResponse", "token", "text"):
                if key in sol:
                    return str(sol[key])
            raise CaptchaSolveError(f"anticaptcha: no token in solution: {sol}")
        raise CaptchaSolveError(f"anticaptcha unexpected status: {data.get('status')}")

    async def get_balance(self) -> float:
        body = {"clientKey": self.api_key}
        async with aiohttp.ClientSession() as session:
            async with session.post(self._BALANCE_URL, json=body) as resp:
                data = await resp.json(content_type=None)
        if data.get("errorId"):
            raise CaptchaSolveError(
                f"anticaptcha balance error: {data.get('errorDescription')}"
            )
        return float(data["balance"])


# ---------------------------------------------------------------------------
# CapSolver
# ---------------------------------------------------------------------------


class CapSolverSolver(BaseSolver):
    _CREATE_URL = "https://api.capsolver.com/createTask"
    _RESULT_URL = "https://api.capsolver.com/getTaskResult"
    _BALANCE_URL = "https://api.capsolver.com/getBalance"

    async def _create_task(self, session: aiohttp.ClientSession, payload: dict) -> str:
        body = {"clientKey": self.api_key, "task": payload}
        async with session.post(self._CREATE_URL, json=body) as resp:
            data = await resp.json(content_type=None)
        if data.get("errorId"):
            raise CaptchaSolveError(
                f"capsolver create failed: {data.get('errorCode')} "
                f"{data.get('errorDescription')}"
            )
        return str(data["taskId"])

    async def _get_result(
        self, session: aiohttp.ClientSession, task_id: str
    ) -> Optional[str]:
        body = {"clientKey": self.api_key, "taskId": task_id}
        async with session.post(self._RESULT_URL, json=body) as resp:
            data = await resp.json(content_type=None)
        if data.get("errorId"):
            raise CaptchaSolveError(
                f"capsolver error: {data.get('errorCode')} "
                f"{data.get('errorDescription')}"
            )
        if data.get("status") == "processing":
            return None
        if data.get("status") == "ready":
            sol = data.get("solution", {})
            for key in ("gRecaptchaResponse", "token", "text"):
                if key in sol:
                    return str(sol[key])
            raise CaptchaSolveError(f"capsolver: no token in solution: {sol}")
        raise CaptchaSolveError(f"capsolver unexpected status: {data.get('status')}")

    async def get_balance(self) -> float:
        body = {"clientKey": self.api_key}
        async with aiohttp.ClientSession() as session:
            async with session.post(self._BALANCE_URL, json=body) as resp:
                data = await resp.json(content_type=None)
        if data.get("errorId"):
            raise CaptchaSolveError(
                f"capsolver balance error: {data.get('errorDescription')}"
            )
        return float(data["balance"])


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------


def _build_backend(
    provider: str, api_key: str, timeout: int, poll_interval: int
) -> BaseSolver:
    if provider == "2captcha":
        return TwoCaptchaSolver(api_key, timeout=timeout, poll_interval=poll_interval)
    if provider == "anticaptcha":
        return AntiCaptchaSolver(api_key, timeout=timeout, poll_interval=poll_interval)
    if provider == "capsolver":
        return CapSolverSolver(api_key, timeout=timeout, poll_interval=poll_interval)
    raise ValueError(
        f"Unknown captcha provider: {provider!r}. "
        f"Supported: {', '.join(_PROVIDERS)}"
    )


class CaptchaSolver:
    """
    Single async entry point for all supported CAPTCHA solver providers.

    Args:
        provider: ``"2captcha"``, ``"anticaptcha"``, or ``"capsolver"``.
        api_key: API key for the chosen provider.
        timeout: Default per-solve timeout in seconds (overridable per call).
        poll_interval: Seconds between result polls.

    Each ``solve_*`` method returns the raw token string. Injecting
    that token back into the page is the caller's responsibility —
    huligan's CDP stealth blocks ``page.evaluate()`` in paranoid mode,
    so the typical pattern is::

        token = await solver.solve_recaptcha_v2(sitekey=..., page_url=page.url)
        await page.locator("textarea#g-recaptcha-response").fill(token)
        # Submit by clicking the form's submit button (page.evaluate / form.submit
        # via evaluate are blocked by patch 05_cdp_stealth in paranoid mode):
        await page.locator("button[type=submit]").click()

    See ``examples/example_captcha.py`` for the full flow.
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        *,
        timeout: int = 120,
        poll_interval: int = 5,
    ):
        if provider not in _PROVIDERS:
            raise ValueError(
                f"Unknown captcha provider: {provider!r}. "
                f"Supported: {', '.join(_PROVIDERS)}"
            )
        self.provider = provider
        self.api_key = api_key
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._backend = _build_backend(provider, api_key, timeout, poll_interval)

    @classmethod
    def from_env(cls, **overrides: Any) -> "CaptchaSolver":
        """
        Build a solver from ``HULIGAN_CAPTCHA_PROVIDER`` and
        ``HULIGAN_CAPTCHA_API_KEY`` env vars. Keyword overrides win.
        """
        provider = overrides.pop("provider", None) or os.environ.get(
            "HULIGAN_CAPTCHA_PROVIDER"
        )
        api_key = overrides.pop("api_key", None) or os.environ.get(
            "HULIGAN_CAPTCHA_API_KEY"
        )
        if not provider:
            raise ValueError(
                "Set HULIGAN_CAPTCHA_PROVIDER or pass provider= explicitly."
            )
        if not api_key:
            raise ValueError(
                "Set HULIGAN_CAPTCHA_API_KEY or pass api_key= explicitly."
            )
        return cls(provider=provider, api_key=api_key, **overrides)

    async def get_balance(self) -> float:
        """Account balance from the configured provider."""
        return await self._backend.get_balance()

    # ----- reCAPTCHA v2 ----------------------------------------------------

    async def solve_recaptcha_v2(
        self,
        sitekey: str,
        page_url: str,
        *,
        invisible: bool = False,
        enterprise: bool = False,
        timeout: Optional[int] = None,
        poll_interval: Optional[int] = None,
    ) -> str:
        if self.provider == "2captcha":
            payload = {
                "method": "userrecaptcha",
                "googlekey": sitekey,
                "pageurl": page_url,
            }
            if invisible:
                payload["invisible"] = "1"
            if enterprise:
                payload["enterprise"] = "1"
        else:
            task_type = (
                "RecaptchaV2EnterpriseTaskProxyless"
                if enterprise
                else "RecaptchaV2TaskProxyless"
            )
            payload = {
                "type": task_type,
                "websiteURL": page_url,
                "websiteKey": sitekey,
                "isInvisible": invisible,
            }
        return await self._backend._run(payload, timeout, poll_interval)

    # ----- reCAPTCHA v3 ----------------------------------------------------

    async def solve_recaptcha_v3(
        self,
        sitekey: str,
        page_url: str,
        *,
        action: str = "verify",
        min_score: float = 0.3,
        enterprise: bool = False,
        timeout: Optional[int] = None,
        poll_interval: Optional[int] = None,
    ) -> str:
        if self.provider == "2captcha":
            payload = {
                "method": "userrecaptcha",
                "version": "v3",
                "googlekey": sitekey,
                "pageurl": page_url,
                "action": action,
                "min_score": str(min_score),
            }
            if enterprise:
                payload["enterprise"] = "1"
        else:
            task_type = (
                "RecaptchaV3EnterpriseTaskProxyless"
                if enterprise
                else "RecaptchaV3TaskProxyless"
            )
            payload = {
                "type": task_type,
                "websiteURL": page_url,
                "websiteKey": sitekey,
                "pageAction": action,
                "minScore": min_score,
            }
        return await self._backend._run(payload, timeout, poll_interval)

    # ----- Cloudflare Turnstile -------------------------------------------

    async def solve_turnstile(
        self,
        sitekey: str,
        page_url: str,
        *,
        action: Optional[str] = None,
        cdata: Optional[str] = None,
        timeout: Optional[int] = None,
        poll_interval: Optional[int] = None,
    ) -> str:
        if self.provider == "2captcha":
            payload = {
                "method": "turnstile",
                "sitekey": sitekey,
                "pageurl": page_url,
            }
            if action:
                payload["action"] = action
            if cdata:
                payload["data"] = cdata
        else:
            payload = {
                "type": "TurnstileTaskProxyless",
                "websiteURL": page_url,
                "websiteKey": sitekey,
            }
            if action:
                payload["action"] = action
            if cdata:
                payload["cData"] = cdata
        return await self._backend._run(payload, timeout, poll_interval)

    # ----- hCaptcha --------------------------------------------------------

    async def solve_hcaptcha(
        self,
        sitekey: str,
        page_url: str,
        *,
        invisible: bool = False,
        timeout: Optional[int] = None,
        poll_interval: Optional[int] = None,
    ) -> str:
        if self.provider == "2captcha":
            payload = {
                "method": "hcaptcha",
                "sitekey": sitekey,
                "pageurl": page_url,
            }
            if invisible:
                payload["invisible"] = "1"
        else:
            payload = {
                "type": "HCaptchaTaskProxyless",
                "websiteURL": page_url,
                "websiteKey": sitekey,
                "isInvisible": invisible,
            }
        return await self._backend._run(payload, timeout, poll_interval)

    # ----- Image / image-with-text ----------------------------------------

    async def solve_image(
        self,
        image_data: bytes,
        *,
        instructions: Optional[str] = None,
        timeout: Optional[int] = None,
        poll_interval: Optional[int] = None,
    ) -> str:
        b64 = base64.b64encode(image_data).decode("ascii")
        if self.provider == "2captcha":
            payload = {"method": "base64", "body": b64}
            if instructions:
                payload["textinstructions"] = instructions
        else:
            payload = {"type": "ImageToTextTask", "body": b64}
            if instructions:
                payload["comment"] = instructions
        return await self._backend._run(payload, timeout, poll_interval)
