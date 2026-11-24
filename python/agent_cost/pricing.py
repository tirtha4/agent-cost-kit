"""Price a call from the API's usage block. $ per million tokens; CHECK the provider's pricing page before trusting these.
Defaults are the Claude Sonnet 5.5 list prices used in the kit's model (Nov 2026)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Price:
    input: float = 2.00
    output: float = 10.00
    cache_read_x: float = 0.10     # cache reads at 10% of input
    cache_write_x: float = 1.25    # 5-minute cache writes at 125% of input (1-hour: 2.0)


SONNET = Price()


def call_cost(usage: Any, price: Price = SONNET) -> float:
    """Dollar cost of one Messages API call. `usage` = response.usage (SDK object) or a dict."""
    g = (lambda k: getattr(usage, k, None) or 0) if not isinstance(usage, dict) else (lambda k: usage.get(k) or 0)
    m = 1e6
    return (g("input_tokens") * price.input + g("cache_read_input_tokens") * price.input * price.cache_read_x
            + g("cache_creation_input_tokens") * price.input * price.cache_write_x + g("output_tokens") * price.output) / m
