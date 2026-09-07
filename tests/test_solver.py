"""Unit tests that stub out the browser and the network.

Run with: pytest -q
"""

import asyncio

import pytest

from camoufox_turnstile import PeakError, solve_turnstile
from camoufox_turnstile import peak, solver


class FakeElement:
    def __init__(self, sitekey):
        self._sitekey = sitekey

    async def get_attribute(self, name):
        return self._sitekey if name == "data-sitekey" else None


class FakePage:
    """Just enough of a Playwright/Camoufox page for the solver."""

    def __init__(self, sitekey=None, existing=None):
        self.url = "https://protected.example/login"
        self._sitekey = sitekey
        self._existing = existing
        self.injected = None

    async def query_selector(self, selector):
        if selector == ".cf-turnstile[data-sitekey]" and self._sitekey:
            return FakeElement(self._sitekey)
        return None

    async def evaluate(self, js, *args):
        if "cf-turnstile-response" in js and "value" in js and not args:
            return self._existing
        if args:  # the inject call
            self.injected = args[0]
            return True
        return self._sitekey  # sitekey fallback read


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_returns_existing_token_without_solving(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should not have called Peak")

    monkeypatch.setattr(peak, "request_token", boom)
    monkeypatch.setattr(solver, "request_token", boom)

    page = FakePage(existing="existing-token-value-0123456789")
    token = run(solve_turnstile(page, api_key="pk_test"))
    assert token == "existing-token-value-0123456789"


def test_solves_and_injects(monkeypatch):
    monkeypatch.setattr(solver, "request_token", lambda *a, **k: "SOLVED-TOKEN")

    page = FakePage(sitekey="0x4AAAAAAABkMYinukE8nzKd")
    token = run(solve_turnstile(page, api_key="pk_test"))
    assert token == "SOLVED-TOKEN"
    assert page.injected == "SOLVED-TOKEN"


def test_raises_when_no_sitekey():
    page = FakePage(sitekey=None)
    with pytest.raises(PeakError):
        run(solve_turnstile(page, api_key="pk_test"))


def test_build_body_shape():
    body = peak.build_body("0xSITEKEY", "https://x.example/", "http://u:p@h:1")
    assert body == {
        "task_type": "turnstiletask",
        "url": "https://x.example/",
        "sitekey": "0xSITEKEY",
        "proxy": "http://u:p@h:1",
    }
