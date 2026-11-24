"""Fix 3 - Clear old information: summarise old tool results, keep the last few in full.

The trap: editing old history changes the prompt prefix, which throws away the cache from that point on (fix 1).
So prune in BATCHES: wait until `prune_at` full results have piled up, then summarise all but the last `keep_last`
in one go. The prefix changes once per batch instead of on every call.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Tuple

Summarizer = Callable[[str], str]


def first_lines_summary(text: str, max_chars: int = 300) -> str:
    """Cheap default: keep the first non-empty lines. Swap in a small-model summary for better recall."""
    body = " ".join(l.strip() for l in text.splitlines() if l.strip())
    return (body[:max_chars] + "…") if len(body) > max_chars else body


def _result_blocks(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for m in messages:
        if m.get("role") == "user" and isinstance(m.get("content"), list):
            out += [b for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
    return out


def _text(block: Dict[str, Any]) -> str:
    c = block.get("content", "")
    if isinstance(c, list):
        return "\n".join(x.get("text", "") for x in c if x.get("type") == "text")
    return str(c)


def prune_tool_results(messages: List[Dict[str, Any]], keep_last: int = 3, prune_at: int = 6,
                       summarize: Summarizer = first_lines_summary) -> Tuple[List[Dict[str, Any]], int]:
    """Return (new_messages, how_many_were_summarised). Leaves `messages` untouched."""
    out = copy.deepcopy(messages)
    full = [b for b in _result_blocks(out) if not b.get("_summary")]
    if len(full) < prune_at:
        return out, 0
    old = full[:-keep_last] if keep_last else full
    for b in old:
        b["content"] = "[summary of an earlier result] " + summarize(_text(b))
        b["_summary"] = True
    return out, len(old)


def strip_private_keys(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove our bookkeeping keys before sending (the API rejects unknown fields)."""
    out = copy.deepcopy(messages)
    for b in _result_blocks(out):
        b.pop("_summary", None)
    return out
