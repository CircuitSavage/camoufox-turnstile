<a href="https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=camoufox-turnstile">
  <img src="https://raw.githubusercontent.com/CircuitSavage/camoufox-turnstile/main/assets/peak-banner.png" alt="Peak — solve Cloudflare Turnstile and the 5s challenge in about a second" width="100%">
</a>

# camoufox-turnstile

Solve Cloudflare Turnstile in [Camoufox](https://github.com/daijro/camoufox) without clicking the widget. It reads the sitekey off the page, gets a token from [Peak](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=camoufox-turnstile), writes it into `cf-turnstile-response`, and fires the widget callback so your submit or navigation goes through.

```python
from camoufox_turnstile import solve_turnstile

token = await solve_turnstile(page, api_key="pk_your_api_key")
```

## Why this exists

Camoufox is a good anti-detect Firefox. Its fingerprint is real enough that plenty of low-risk Turnstile widgets pass on their own, and this package leans on that: it checks whether the response field is already filled and, if it is, hands you that token for free.

The wall shows up when the widget scores the session as risky. Turnstile weighs the IP and the session history, not the checkbox. From a datacenter IP with no trusted past, a fresh Camoufox session gets held at the "Verifying..." spinner or looped through an invisible challenge that never resolves. Waiting longer does nothing, because the token you need is minted by Cloudflare's risk engine, not by the interaction.

So when the native pass stalls, this reads the sitekey, sends it to Peak, and injects the token Cloudflare's `siteverify` will accept. Drop in an API key and the blocked run keeps moving.

## Install

```bash
pip install camoufox-turnstile camoufox[geoip]
python -m camoufox fetch   # one-time: pull the patched Firefox build
```

The package itself has no runtime dependencies — it drives the Camoufox page you already have. `camoufox` is the browser you run it against.

## Quickstart

```python
import asyncio
import os
from camoufox.async_api import AsyncCamoufox
from camoufox_turnstile import solve_turnstile

async def main():
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        page = await browser.new_page()
        await page.goto("https://protected.example/login")
        await page.wait_for_timeout(2500)  # let the widget render / self-pass

        # Returns an already-earned token if Camoufox passed on its own,
        # otherwise reads the sitekey, solves via Peak, injects the token.
        await solve_turnstile(page, api_key=os.environ["PEAK_API_KEY"])

        await page.click("button[type=submit]")
        await page.wait_for_load_state("networkidle")

asyncio.run(main())
```

Set the key once and let it read from the environment:

```bash
export PEAK_API_KEY=pk_your_api_key   # Windows: set PEAK_API_KEY=pk_your_api_key
```

```python
await solve_turnstile(page)  # picks up PEAK_API_KEY
```

A full runnable script is in [`examples/camoufox_example.py`](./examples/camoufox_example.py).

## Native pass vs. an API solve

Camoufox and Peak cover different failure modes. Use them together.

- **Let Camoufox try first.** Launch with `humanize=True`, a real locale, and — for anything that matters — a residential or ISP proxy. A clean fingerprint on a residential IP clears most non-interactive widgets with no solve at all. `solve_turnstile` returns that free token when it finds one.
- **Solve through Peak when it stalls.** Datacenter egress, a high-risk sitekey, or an aggressive site will hold the widget open no matter how good the browser is. That is the case Peak handles: it returns a token minted against the sitekey, independent of your browser session.
- **Match the egress.** If you pass a `proxy` to Peak, use the same IP the browser goes out on. A token solved from one network and replayed from another is more likely to be rejected server-side.

## What it does not do

- **Not the full-page interstitial.** The Cloudflare "Just a moment" page that gates a whole domain and sets `cf_clearance` is a different challenge from an embedded Turnstile widget. This package handles the widget — the one that renders a `cf-turnstile` element and a `cf-turnstile-response` field. For the interstitial, Peak has a separate `cloudflare5stask`; see the [docs](https://peak.fo/docs/turnstile?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=camoufox-turnstile).
- **Not reCAPTCHA or hCaptcha.** Turnstile only.
- **No magic on a banned IP.** If the target has already blocked your IP range, get a better egress first. A valid token on a burned network still gets refused.

## API

### `await solve_turnstile(page, api_key=None, proxy=None, sitekey=None, timeout=180.0, use_existing=True)`

Get a valid Turnstile token onto a Camoufox `page` and inject it. Returns the token.

- `page` — a Camoufox (Playwright async) `Page` on a Turnstile-gated URL.
- `api_key` — Peak key (`pk_...`). Falls back to `PEAK_API_KEY`.
- `proxy` — optional proxy handed to Peak, e.g. `http://user:pass@host:port`. Use the same egress as the browser.
- `sitekey` — skip the DOM read and use this sitekey.
- `timeout` — seconds to wait on Peak.
- `use_existing` — if `True` (default), return a token Camoufox already earned instead of paying for a solve.

### `await read_sitekey(page)`

Return the Turnstile sitekey rendered on the page (from `.cf-turnstile[data-sitekey]`, any `[data-sitekey]`, or the `challenges.cloudflare.com` iframe `src`), or `None`.

### `await existing_token(page)`

Return the token in `cf-turnstile-response` if Camoufox already passed the widget, else `None`.

### `await inject_token(page, token)`

Write `token` into the response field(s) and fire the widget's `data-callback`. Returns `True` if a callback was found and called.

### `request_token(sitekey, url, api_key=None, proxy=None, timeout=180.0)`

The raw, blocking Peak call, in case you want the token without a page. Returns the token string or raises `PeakError`.

## How it works

1. If `use_existing`, read `cf-turnstile-response`; a filled field means Camoufox already passed, so return that token and skip the solve.
2. Read the sitekey from the widget, or scrape it from the Cloudflare iframe `src` when the widget rendered implicitly.
3. Call Peak `POST https://api.peak.fo/solve` with `task_type: "turnstiletask"`, the `sitekey`, `url: page.url`, and your optional `proxy` — over `X-API-Key`. Peak returns `{"success": true, "data": {"token": "..."}}`.
4. Inject the token into every `cf-turnstile-response` field (creating a hidden input if the widget hasn't rendered one) and invoke the widget's `data-callback`, so the host page's success handler runs.

The solve call blocks, so the async path runs it in a worker thread and never stalls the browser's event loop.

## Powered by Peak

This uses [Peak](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=camoufox-turnstile), a Cloudflare specialist that returns a Turnstile token in about a second.

- **$0.90 per 1,000** successful Turnstile solves, down to **$0.35 at volume**.
- **Pay only for successes** — a failed solve is not billed.
- **About 1,000 free solves** to start, no card.

→ [Get a free API key](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=camoufox-turnstile) · [Turnstile docs](https://peak.fo/docs/turnstile?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=camoufox-turnstile)

## Other Peak wrappers

Same solve, wired into other stacks:

- [playwright-turnstile](https://github.com/CircuitSavage/playwright-turnstile) — token injection for Playwright.
- [selenium-turnstile](https://github.com/CircuitSavage/selenium-turnstile) — a valid token in Selenium, no physical click.
- [scrapy-turnstile](https://github.com/CircuitSavage/scrapy-turnstile) — Scrapy middleware that keeps blocked spiders running.
- [puppeteer-extra-plugin-turnstile](https://github.com/CircuitSavage/puppeteer-extra-plugin-turnstile) — a `puppeteer-extra` plugin.
- [turnstile-curl](https://github.com/CircuitSavage/turnstile-curl) — solve from `curl_cffi`, no browser.
- [cloudscraper-turnstile](https://github.com/CircuitSavage/cloudscraper-turnstile) — a `cloudscraper` drop-in.
- [crawl4ai-turnstile](https://github.com/CircuitSavage/crawl4ai-turnstile) — Turnstile solving for Crawl4AI.

More on the list: [awesome-turnstile-solvers](https://github.com/CircuitSavage/awesome-turnstile-solvers).

## Legitimate use

Built for automation, QA, and scraping public data. Respect each site's Terms of Service and `robots.txt`, and don't point it at credential-stuffing or other abuse. How you use it is on you.

## License

MIT — see [LICENSE](./LICENSE).
