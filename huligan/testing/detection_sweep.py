"""Detection-sweep harness: normalized verdicts across N detection sites.

AUXILIARY signal only. Every rung reads a live third-party detector over CDP, which
this project has repeatedly seen return a stale/frozen snapshot ("false 100%"). An
operator's visual read of the headed window is authoritative; a green sweep never
overrides it, a red/warn sweep is a hint to go look. Run headed + manual; do not gate CI.

Reads use a layered reader that never calls ``page.evaluate()`` (which hangs under the
default paranoid ``cdp_mode``): DOM text via locators, or a raw CDP ``Runtime.evaluate``
through ``page.context.new_cdp_session`` (the call still works; only the main-world
``executionContextCreated`` event is suppressed). Adapters default to ``error`` when their
signal is missing, so a scrape miss never masquerades as a pass.

NOTE: the exact selectors / internal-object paths below are best-effort and must be
confirmed against the live sites (detectors change class names and globals often). Run
``examples/detection_sweep.py --headed`` and refine per site.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

Verdict = str  # "pass" | "warn" | "fail" | "error"

_ICON = {"pass": "[OK]", "warn": "[!!]", "fail": "[XX]", "error": "[??]"}


@dataclass
class SiteVerdict:
    site: str
    url: str
    verdict: Verdict
    raw: object = None
    notes: List[str] = field(default_factory=list)
    allowlisted: List[str] = field(default_factory=list)
    elapsed_ms: int = 0


# Per-site map of check-ids that are known-benign for our build. An allowlisted check is
# downgraded fail -> warn, kept visible in notes, and excluded from the fail counter. It is
# the ONLY way a sub-check is downgraded (never silently dropped), so a newly-broken check
# is never hidden by a stale entry.
ALLOWLIST = {
    "deviceandbrowserinfo": {
        "connectionRTT": "navigator.connection.rtt rounded to 0 by design - benign",
    },
    "sannysoft": {
        "WEBDRIVER_NEW": "new-headless webdriver row - benign for our build",
    },
}


def apply_allowlist(site: str, failed_check_ids: List[str]) -> (List[str], List[str]):
    """Split failed check-ids into (still-failing, allowlisted-downgraded) for a site."""
    site_allow = ALLOWLIST.get(site, {})
    still_failing, downgraded = [], []
    for cid in failed_check_ids:
        (downgraded if cid in site_allow else still_failing).append(cid)
    return still_failing, downgraded


# --- layered reader (never page.evaluate) ---------------------------------

async def _dom_text(page, selector: str, timeout: float = 8000) -> Optional[str]:
    try:
        return await page.locator(selector).first.text_content(timeout=timeout)
    except Exception:
        return None


async def _cdp_eval(page, expression: str):
    """Read a JS value via a raw CDP session (survives paranoid; not page.evaluate)."""
    try:
        cdp = await page.context.new_cdp_session(page)
        r = await cdp.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return r.get("result", {}).get("value")
    except Exception:
        return None


# --- adapters -------------------------------------------------------------

class Adapter:
    site = ""
    url = ""
    needs_proxy = False

    async def _read(self, page) -> SiteVerdict:  # override
        raise NotImplementedError

    async def run(self, page) -> SiteVerdict:
        start = time.monotonic()
        try:
            await page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(4000)  # settle; detectors run async after load
            sv = await self._read(page)
        except Exception as e:
            sv = SiteVerdict(self.site, self.url, "error", raw=repr(e),
                             notes=[f"adapter error: {e}"])
        sv.elapsed_ms = int((time.monotonic() - start) * 1000)
        return sv


class BrowserScan(Adapter):
    site, url = "browserscan", "https://www.browserscan.net/bot-detection"

    async def _read(self, page) -> SiteVerdict:
        text = await _dom_text(page, "body") or ""
        m = re.search(r"(\d{1,3})\s*%", text)
        if not m:
            return SiteVerdict(self.site, self.url, "error", raw=text[:200],
                               notes=["score % not found (confirm selector live)"])
        score = int(m.group(1))
        verdict = "pass" if score >= 95 else ("warn" if score >= 80 else "fail")
        return SiteVerdict(self.site, self.url, verdict, raw={"score": score},
                           notes=[f"score {score}%"])


class SannySoft(Adapter):
    site, url = "sannysoft", "https://bot.sannysoft.com/"

    async def _read(self, page) -> SiteVerdict:
        # Count green/red result cells via a raw-CDP DOM walk (test_sannysoft_rebrowser pattern).
        expr = (
            "(function(){var g=0,r=0;"
            "document.querySelectorAll('td').forEach(function(td){"
            "var bg=(td.style && td.style.background||'')+'';"
            "if(/rgb\\(0,\\s*255|lightgreen|#0f0|green/i.test(bg))g++;"
            "if(/rgb\\(255,\\s*0|red|#f00/i.test(bg))r++;});"
            "return JSON.stringify({green:g,red:r});})()"
        )
        raw = await _cdp_eval(page, expr)
        try:
            data = json.loads(raw) if raw else None
        except Exception:
            data = None
        if not data:
            return SiteVerdict(self.site, self.url, "error",
                               notes=["could not read result table (confirm live)"])
        failed = ["WEBDRIVER_NEW"] if data["red"] else []
        still, downgraded = apply_allowlist(self.site, failed)
        verdict = "fail" if still else ("warn" if downgraded else "pass")
        return SiteVerdict(self.site, self.url, verdict, raw=data,
                           notes=[f"green {data['green']} / red {data['red']}"],
                           allowlisted=downgraded)


class CreepJS(Adapter):
    site, url = "creepjs", "https://abrahamjuliot.github.io/creepjs/"

    async def _read(self, page) -> SiteVerdict:
        await page.wait_for_timeout(4000)  # creepjs is slow to compute
        text = await _dom_text(page, "body") or ""
        lies = None
        m = re.search(r"(\d+)\s*lies", text, re.IGNORECASE)
        if m:
            lies = int(m.group(1))
        trust = None
        mt = re.search(r"trust score[:\s]*([0-9.]+%?)", text, re.IGNORECASE)
        if mt:
            trust = mt.group(1)
        if lies is None:
            return SiteVerdict(self.site, self.url, "error", raw=text[:200],
                               notes=["lies count not found (confirm selector live)"])
        verdict = "pass" if lies == 0 else ("warn" if lies <= 2 else "fail")
        return SiteVerdict(self.site, self.url, verdict, raw={"lies": lies, "trust": trust},
                           notes=[f"lies {lies}" + (f" / trust {trust}" if trust else "")])


class Rebrowser(Adapter):
    site, url = "rebrowser", "https://bot-detector.rebrowser.net/"

    async def _read(self, page) -> SiteVerdict:
        # Per-test results object (keys illustrative — confirm live).
        expr = "JSON.stringify(window.results || window.detectionResults || null)"
        raw = await _cdp_eval(page, expr)
        if not raw or raw == "null":
            text = await _dom_text(page, "body") or ""
            leaks = len(re.findall(r"\b(detected|leak|fail)\b", text, re.IGNORECASE))
            verdict = "pass" if leaks == 0 else "warn"
            return SiteVerdict(self.site, self.url, verdict, raw=text[:200],
                               notes=[f"DOM fallback: {leaks} leak-ish keywords (confirm live)"])
        try:
            data = json.loads(raw)
        except Exception:
            data = raw
        return SiteVerdict(self.site, self.url, "warn", raw=data,
                           notes=["read results object - map keys to pass/fail live"])


class Incolumitas(Adapter):
    site, url = "incolumitas", "https://bot.incolumitas.com/"

    async def _read(self, page) -> SiteVerdict:
        await page.wait_for_timeout(6000)  # runs a behavioral test over time
        expr = "JSON.stringify((window.tests || window.detectionTests || {}))"
        raw = await _cdp_eval(page, expr)
        text = await _dom_text(page, "body") or ""
        m = re.search(r"behav\w*\s*score[:\s]*([0-9.]+)", text, re.IGNORECASE)
        if not raw and not m:
            return SiteVerdict(self.site, self.url, "error", raw=text[:200],
                               notes=["no score / tests object (confirm live)"])
        note = "read internal tests object" if raw and raw != "null" else f"behavior score {m.group(1) if m else '?'}"
        return SiteVerdict(self.site, self.url, "warn", raw=(raw or text[:200]),
                           notes=[note + " - map to pass/fail live"])


class DeviceAndBrowserInfo(Adapter):
    site, url = "deviceandbrowserinfo", "https://deviceandbrowserinfo.com/are_you_a_bot"

    async def _read(self, page) -> SiteVerdict:
        # fp.platformEstimate + bot verdict (paths illustrative - confirm live).
        estimate = await _cdp_eval(page, "JSON.stringify(window.fp?.platformEstimate ?? null)")
        text = await _dom_text(page, "body") or ""
        is_bot = bool(re.search(r"you\s+are\s+a?\s*bot", text, re.IGNORECASE)) and \
            not re.search(r"not\s+a?\s*bot", text, re.IGNORECASE)
        failed = ["connectionRTT"] if re.search(r"connectionRTT", text) else []
        still, downgraded = apply_allowlist(self.site, failed)
        if is_bot or still:
            verdict = "fail"
        elif downgraded:
            verdict = "warn"
        else:
            verdict = "pass"
        return SiteVerdict(self.site, self.url, verdict,
                           raw={"platformEstimate": estimate, "bot": is_bot},
                           notes=[f"bot: {'yes' if is_bot else 'no'}"],
                           allowlisted=downgraded)


class PixelScan(Adapter):
    site, url, needs_proxy = "pixelscan", "https://pixelscan.net/", True

    async def _read(self, page) -> SiteVerdict:
        text = (await _dom_text(page, "body") or "").lower()
        if "masking" in text and "detected" in text:
            return SiteVerdict(self.site, self.url, "fail", notes=["masking detected"])
        if "consistent" in text:
            return SiteVerdict(self.site, self.url, "pass", notes=["consistent"])
        return SiteVerdict(self.site, self.url, "error",
                           notes=["no verdict (needs residential proxy)"])


_DEFAULT_ADAPTERS = [BrowserScan(), SannySoft(), CreepJS(), Rebrowser(),
                     Incolumitas(), DeviceAndBrowserInfo()]
_ALL_ADAPTERS = _DEFAULT_ADAPTERS + [PixelScan()]


async def run_sweep(browser, sites: Optional[List[str]] = None) -> List[SiteVerdict]:
    """Run each adapter sequentially against ONE page. ``browser`` is a huligan.Browser.

    ``sites`` optionally restricts/extends to named adapters (e.g. ["creepjs","pixelscan"]).
    """
    adapters = _ALL_ADAPTERS if sites else _DEFAULT_ADAPTERS
    if sites:
        want = set(sites)
        adapters = [a for a in _ALL_ADAPTERS if a.site in want]
    page = await browser.new_page()
    results = []
    for adapter in adapters:
        results.append(await adapter.run(page))
    return results


# --- reporting ------------------------------------------------------------

def _counts(results: List[SiteVerdict]) -> dict:
    out = {"pass": 0, "warn": 0, "fail": 0, "error": 0}
    for r in results:
        out[r.verdict] = out.get(r.verdict, 0) + 1
    return out


def render_summary(results: List[SiteVerdict]) -> str:
    lines = [
        "DETECTION SWEEP  (headed - paranoid CDP - AUXILIARY, not authoritative)",
    ]
    for r in results:
        note = "; ".join(r.notes) if r.notes else ""
        al = f"   [allowlisted: {', '.join(r.allowlisted)}]" if r.allowlisted else ""
        lines.append(f"  {_ICON.get(r.verdict, '[??]')} {r.site:<22} {note}{al}")
    c = _counts(results)
    lines.append("  " + "-" * 52)
    lines.append(f"  PASS {c['pass']} - WARN {c['warn']} - FAIL {c['fail']} - "
                 f"ERROR {c['error']}   over {len(results)} sites")
    lines.append("  Reminder: operator visual read of the headed window is authoritative.")
    return "\n".join(lines)


def to_json(results: List[SiteVerdict]) -> str:
    return json.dumps({
        "summary": _counts(results),
        "sites": [
            {"site": r.site, "url": r.url, "verdict": r.verdict, "raw": r.raw,
             "notes": r.notes, "allowlisted": r.allowlisted, "elapsed_ms": r.elapsed_ms}
            for r in results
        ],
    }, indent=2, default=str)
