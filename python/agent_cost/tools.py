"""Fix 6 - Only send the tools this step needs.

Every tool definition (name, description, JSON schema) is input tokens on EVERY request, whether or not the tool is
called. 100 tools at ~500 tokens each is ~50,000 tokens before the agent has read anything.
Pick a small set per step: a few always-on tools plus the best matches for the current step.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List

from .trim import estimate_tokens

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "to", "of", "and", "or", "in", "on", "for", "with", "this", "that", "it", "is", "be", "use", "when", "from", "by", "as"}


def tool_tokens(tools: List[Dict[str, Any]]) -> int:
    """Approximate tokens the tool list adds to every request."""
    return estimate_tokens(json.dumps(tools))


def _words(s: str) -> set:
    return {w for w in _WORD.findall(s.lower()) if w not in _STOP and len(w) > 2}


def select_tools(tools: List[Dict[str, Any]], step: str, k: int = 5, always: Iterable[str] = ()) -> List[Dict[str, Any]]:
    """Keep `always` tools plus the top-k by word overlap between the step and each tool's name + description.
    Good enough for most agents; swap the scorer for embeddings when you have hundreds of similar tools."""
    always = set(always)
    want = _words(step)
    scored = []
    for t in tools:
        if t["name"] in always:
            continue
        text = t["name"].replace("_", " ") + " " + t.get("description", "")
        score = len(want & _words(text))
        if score:
            scored.append((score, t["name"], t))
    scored.sort(key=lambda x: (-x[0], x[1]))
    keep = {t["name"] for t in tools if t["name"] in always} | {n for _, n, _ in scored[:k]}
    return [t for t in tools if t["name"] in keep]
