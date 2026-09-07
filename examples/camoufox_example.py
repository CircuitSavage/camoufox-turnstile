"""Launch Camoufox, hit a Turnstile-gated page, solve, and continue.

    pip install camoufox[geoip] camoufox-turnstile
    python -m camoufox fetch          # one-time: download the Firefox build
    export PEAK_API_KEY=pk_your_key   # Windows: set PEAK_API_KEY=pk_your_key
    python camoufox_example.py
"""

import asyncio
import os

from camoufox.async_api import AsyncCamoufox

from camoufox_turnstile import solve_turnstile

TARGET = "https://protected.example/login"

# Send Peak the same egress the browser uses, so the token matches the session.
# Leave as None to solve proxyless.
PROXY = None  # e.g. "http://user:pass@host:port"


async def main() -> None:
    async with AsyncCamoufox(headless=True, humanize=True, proxy=PROXY) as browser:
        page = await browser.new_page()
        await page.goto(TARGET, wait_until="domcontentloaded")

        # Give the widget a moment to render, then let Camoufox try on its own.
        await page.wait_for_timeout(2500)

        token = await solve_turnstile(
            page,
            api_key=os.environ.get("PEAK_API_KEY"),
            proxy=PROXY,
        )
        print(f"turnstile token: {token[:24]}... ({len(token)} chars)")

        # The token is injected and the widget callback has fired. Submit or
        # navigate the way the page expects.
        await page.click("button[type=submit]")
        await page.wait_for_load_state("networkidle")
        print("landed on:", page.url)


if __name__ == "__main__":
    asyncio.run(main())
