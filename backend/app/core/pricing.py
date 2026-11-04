"""Gemini list prices, for cost estimates only (D62).

Prices are US dollars per million tokens on the paid standard tier, from
https://ai.google.dev/gemini-api/docs/pricing, checked on the date below.
Output prices include thinking tokens. The free tier costs nothing but may
use the data to improve Google's products (docs/SECURITY.md). A model not
listed here gives no estimate rather than a guessed one.
"""

PRICES_CHECKED = "2026-11-05"
# model: (input, output) in USD per million tokens
PRICES_USD_PER_M: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),  # introductory price until 31 Dec 2026
    "gemini-embedding-2": (0.20, 0.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """`output_tokens` must include thinking tokens: Google bills them as output."""
    price = PRICES_USD_PER_M.get(model)
    if price is None:
        return None
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
