"""Minimal client for the Peak solve API (https://peak.fo).

Standard library only, so pulling this in never drags extra packages into your
Camoufox environment. The network call blocks, so the async solver runs it in a
worker thread and keeps the browser's event loop free.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

SOLVE_URL = "https://api.peak.fo/solve"
DEFAULT_TIMEOUT = 180.0


class PeakError(RuntimeError):
    """Peak returned an error, or the request never got through."""


def resolve_api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get("PEAK_API_KEY")
    if not key:
        raise PeakError(
            "No Peak API key. Pass api_key=... or set PEAK_API_KEY. "
            "Grab a free one at https://peak.fo."
        )
    return key


def build_body(sitekey: str, url: str, proxy: str | None) -> dict:
    """Assemble the /solve request body for a Turnstile task."""
    body = {"task_type": "turnstiletask", "url": url, "sitekey": sitekey}
    if proxy:
        body["proxy"] = proxy
    return body


def request_token(
    sitekey: str,
    url: str,
    api_key: str | None = None,
    proxy: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Ask Peak for a Turnstile token. Blocking; returns the token string.

    Raises PeakError on a transport failure, a non-200, or a failed solve.
    Failed solves come back with success=false and are not billed.
    """
    key = resolve_api_key(api_key)
    data = json.dumps(build_body(sitekey, url, proxy)).encode("utf-8")
    req = urllib.request.Request(
        SOLVE_URL,
        data=data,
        method="POST",
        headers={
            "X-API-Key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        body = exc.read().decode("utf-8", "replace")
        raise PeakError(f"Peak HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network path
        raise PeakError(f"Could not reach Peak: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PeakError(f"Peak sent back non-JSON: {raw!r}") from exc

    if not payload.get("success"):
        raise PeakError(f"Solve failed: {payload.get('error', 'unknown error')}")

    token = (payload.get("data") or {}).get("token")
    if not token:
        raise PeakError(f"No token in Peak response: {payload!r}")
    return token
