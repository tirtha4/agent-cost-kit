"""Fix 2 - Send the 20 lines that matter, not the 2,000-line log.

Every tool result stays in the conversation and is re-sent on every later call, so a fat result is paid for again and
again. Trim it before it goes back to the model: keep the windows around errors, or the head and tail when nothing
matches, and say how much was cut so the model can ask for more.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Tuple

DEFAULT_PATTERNS = (r"\berror\b", r"\bfail(ed|ure|ing)?\b", r"\bexception\b", r"traceback", r"\bpanic\b", r"✖", r"assert", r"\bwarn(ing)?\b")


def estimate_tokens(text: str) -> int:
    """Rough count (about 4 characters per token for English and code). Use the provider's token counter for exact numbers."""
    return max(1, len(text) // 4) if text else 0


def _windows(n: int, hits: Iterable[int], before: int, after: int) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    for h in sorted(hits):
        a, b = max(0, h - before), min(n, h + after + 1)
        if spans and a <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], b))
        else:
            spans.append((a, b))
    return spans


def trim_output(text: str, max_lines: int = 80, patterns: Iterable[str] = DEFAULT_PATTERNS, before: int = 3, after: int = 16,
                head: int = 10, tail: int = 20, max_windows: int = 4) -> str:
    """Return `text` unchanged if it is short; otherwise only the parts worth reading, with line numbers and a note."""
    lines = text.splitlines()
    n = len(lines)
    if n <= max_lines:
        return text
    rx = re.compile("|".join(patterns), re.IGNORECASE)
    hits = [i for i, l in enumerate(lines) if rx.search(l)]
    if hits:
        spans = _windows(n, hits, before, after)[:max_windows]
    else:
        spans = [(0, min(head, n)), (max(0, n - tail), n)]
    kept: List[str] = []
    for a, b in spans:
        if kept:
            kept.append("…")
        kept += [f"{i + 1}: {lines[i]}" for i in range(a, b)]
    shown = sum(b - a for a, b in spans)
    note = f"[trimmed: showing {shown} of {n} lines" + (f" around {len(hits)} matches" if hits else ", head and tail") + "; ask for a line range if you need more]"
    return note + "\n" + "\n".join(kept)


def cap_tokens(text: str, max_tokens: int = 2000) -> str:
    """Hard ceiling for any tool result (JSON blobs, web pages): keep the start and the end."""
    if estimate_tokens(text) <= max_tokens:
        return text
    keep = max_tokens * 4 // 2
    return text[:keep] + f"\n…[{estimate_tokens(text) - max_tokens} tokens cut]…\n" + text[-keep:]
