"""Fix 1 - Cache the prefix that never changes.

Claude builds its cache in this order: tools -> system -> messages. A `cache_control` breakpoint caches everything
before it, so put the stable parts first and mark the end of them once:

    tools      (same every call)        \
    system     (same every call)         } cached: later calls pay 10% of the input price for these tokens
    messages   (grows every call)       /  <- optional rolling breakpoint on the newest turn

Prices (Anthropic, check the pricing page): cache read = 0.1x input, 5-minute cache write = 1.25x, 1-hour write = 2x.
Prompts shorter than the model's minimum cacheable length (about 1,024 tokens on Sonnet/Opus) are not cached.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


def _cc(ttl: Optional[str]) -> Dict[str, Any]:
    return {"type": "ephemeral", **({"ttl": ttl} if ttl else {})}


def cached_system(text: str, ttl: Optional[str] = None) -> List[Dict[str, Any]]:
    """System prompt as one cached block. Because tools come before system, this also caches the tool definitions."""
    return [{"type": "text", "text": text, "cache_control": _cc(ttl)}]


def cache_tools(tools: List[Dict[str, Any]], ttl: Optional[str] = None) -> List[Dict[str, Any]]:
    """Mark the last tool definition, for runs where the system prompt changes but the tools don't."""
    out = copy.deepcopy(tools)
    if out:
        out[-1]["cache_control"] = _cc(ttl)
    return out


def cache_latest_turn(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rolling breakpoint: mark the last block of the newest message so the whole history so far is reused next call.
    Removes older rolling marks first (Claude allows at most 4 breakpoints per request)."""
    out = copy.deepcopy(messages)
    for m in out:
        if isinstance(m.get("content"), list):
            for b in m["content"]:
                if isinstance(b, dict):
                    b.pop("cache_control", None)
    if out:
        last = out[-1]
        if isinstance(last["content"], str):
            last["content"] = [{"type": "text", "text": last["content"]}]
        if isinstance(last["content"][-1], dict):          # user turns are plain dicts (tool results, text)
            last["content"][-1]["cache_control"] = _cc(None)
    return out


def cache_report(usage: Any) -> Dict[str, float]:
    """How much of this call's input came from the cache. Works with the SDK's Usage object or a plain dict."""
    g = (lambda k: getattr(usage, k, None) or 0) if not isinstance(usage, dict) else (lambda k: usage.get(k) or 0)
    read, write, fresh = g("cache_read_input_tokens"), g("cache_creation_input_tokens"), g("input_tokens")
    total = read + write + fresh
    return {"cache_read": read, "cache_write": write, "uncached": fresh, "hit_ratio": round(read / total, 3) if total else 0.0}
