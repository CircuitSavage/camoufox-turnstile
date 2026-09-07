"""Turnstile helpers for a Camoufox page.

Camoufox hands you a Playwright page backed by a real, fingerprint-patched
Firefox, so the flow here is DOM-first: read the sitekey off the widget, get a
token from Peak, write it into ``cf-turnstile-response`` and fire the widget
callback. No clicking, no waiting on a spinner that will never resolve from a
datacenter IP.
"""

from __future__ import annotations

import asyncio

from .peak import PeakError, request_token

# Where the sitekey tends to live once Turnstile has rendered.
_SITEKEY_SELECTORS = (
    ".cf-turnstile[data-sitekey]",
    "[data-sitekey]",
    "iframe[src*='challenges.cloudflare.com']",
)

# Pull the sitekey in-page for the cases an element attribute won't cover:
# implicit render, an iframe-only widget, or turnstile.render() config.
_READ_SITEKEY_JS = r"""() => {
  const el = document.querySelector('[data-sitekey]');
  if (el) return el.getAttribute('data-sitekey');
  const frame = document.querySelector("iframe[src*='challenges.cloudflare.com']");
  if (frame) {
    const m = (frame.getAttribute('src') || '').match(/[?&]sitekey=([^&]+)/);
    if (m) return decodeURIComponent(m[1]);
  }
  return null;
}"""

# If Camoufox already passed Turnstile on its own, the response field is filled.
# Read it so we can skip a paid solve entirely.
_READ_EXISTING_TOKEN_JS = r"""() => {
  const f = document.querySelector('[name="cf-turnstile-response"]');
  const v = f && f.value ? f.value.trim() : '';
  return v.length > 20 ? v : null;
}"""

# Write the token into every response field (making a hidden input if the widget
# hasn't rendered one), then call the widget's data-callback so the host page's
# own success handler runs.
_INJECT_TOKEN_JS = r"""(token) => {
  const name = 'cf-turnstile-response';
  let fields = Array.from(document.querySelectorAll(`[name="${name}"]`));
  if (fields.length === 0) {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = name;
    (document.querySelector('form') || document.body).appendChild(input);
    fields = [input];
  }
  for (const f of fields) {
    f.value = token;
    f.dispatchEvent(new Event('input', { bubbles: true }));
    f.dispatchEvent(new Event('change', { bubbles: true }));
  }

  let callbackFired = false;
  const widget = document.querySelector('.cf-turnstile[data-callback], [data-callback]');
  if (widget) {
    const cb = widget.getAttribute('data-callback');
    if (cb && typeof window[cb] === 'function') {
      try { window[cb](token); callbackFired = true; } catch (e) {}
    }
  }
  return callbackFired;
}"""


async def read_sitekey(page) -> str | None:
    """Return the Turnstile sitekey rendered on ``page``, or None."""
    for selector in _SITEKEY_SELECTORS:
        element = await page.query_selector(selector)
        if element is None:
            continue
        try:
            sitekey = await element.get_attribute("data-sitekey")
        except Exception:
            sitekey = None
        if sitekey:
            return sitekey
    return await page.evaluate(_READ_SITEKEY_JS)


async def existing_token(page) -> str | None:
    """Return a token Camoufox already earned on its own, if the field is set.

    Camoufox's fingerprint is good enough that many low-risk widgets clear
    without help. Check here first and you avoid paying for a solve you don't
    need.
    """
    try:
        return await page.evaluate(_READ_EXISTING_TOKEN_JS)
    except Exception:
        return None


async def inject_token(page, token: str) -> bool:
    """Write ``token`` into the response field(s) and fire the widget callback.

    Returns True if a ``data-callback`` was found and invoked.
    """
    return bool(await page.evaluate(_INJECT_TOKEN_JS, token))


async def solve_turnstile(
    page,
    api_key: str | None = None,
    proxy: str | None = None,
    sitekey: str | None = None,
    timeout: float = 180.0,
    use_existing: bool = True,
) -> str:
    """Get a valid Turnstile token onto a Camoufox ``page``.

    Order of play: if Camoufox already filled ``cf-turnstile-response`` and
    ``use_existing`` is set, return that token untouched. Otherwise read the
    sitekey, ask Peak for a token, inject it, and fire the widget callback so
    your submit or navigation goes through.

    Args:
        page: A Camoufox (Playwright async) ``Page`` on a Turnstile-gated URL.
        api_key: Peak key (``pk_...``). Falls back to ``PEAK_API_KEY``.
        proxy: Proxy to hand Peak, e.g. ``http://user:pass@host:port``. Use the
            same egress the browser uses so the token matches the session.
        sitekey: Skip the DOM read and use this sitekey.
        timeout: Seconds to wait on Peak.
        use_existing: Return a token Camoufox already earned instead of solving.

    Returns:
        The Turnstile token (also injected into the page).

    Raises:
        PeakError: no sitekey on the page, or Peak could not solve it.
    """
    if use_existing:
        already = await existing_token(page)
        if already:
            return already

    if sitekey is None:
        sitekey = await read_sitekey(page)
    if not sitekey:
        raise PeakError(
            "No Turnstile sitekey on the page. Has the widget rendered yet? "
            "Pass sitekey=... if you already know it."
        )

    token = await asyncio.to_thread(
        request_token,
        sitekey,
        page.url,
        api_key=api_key,
        proxy=proxy,
        timeout=timeout,
    )
    await inject_token(page, token)
    return token
