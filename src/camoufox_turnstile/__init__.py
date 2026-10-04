"""camoufox-turnstile — solve Cloudflare Turnstile in Camoufox via Peak.

Read the sitekey, solve through the Peak API, inject the token, keep scraping.
"""

from .peak import PeakError, request_token
from .solver import (
    existing_token,
    inject_token,
    read_sitekey,
    solve_turnstile,
)

__all__ = [
    "solve_turnstile",
    "read_sitekey",
    "existing_token",
    "inject_token",
    "request_token",
    "PeakError",
]

__version__ = "0.1.1"
