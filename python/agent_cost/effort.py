"""Fix 7 - Match reasoning effort to the task.

Thinking tokens are billed as OUTPUT (the expensive side). Extracting an email, sorting a ticket or classifying a
message doesn't need the reasoning budget you'd give a hard debugging task.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

LOW = r"\b(extract|classif\w*|sort|tag|label|route|format|rename|translate|lookup|look up|search|find|list|count|convert)\b"
HIGH = r"\b(debug|refactor|architect\w*|design|plan|prove|migrat\w*|optimi[sz]e|security|review|root cause|race condition)\b"


def pick_effort(task: str) -> str:
    """'low' | 'medium' | 'high' from the task text. Override it whenever you know better."""
    t = task.lower()
    if re.search(HIGH, t):
        return "high"
    if re.search(LOW, t):
        return "low"
    return "medium"


def anthropic_thinking(effort: str) -> Optional[Dict[str, Any]]:
    """Claude extended thinking: no thinking for low, a budget for medium/high (budget_tokens must stay below max_tokens).
    Pass as `thinking=...` only when not None. Newer Claude models also take an effort setting; see the API docs."""
    return {"low": None, "medium": {"type": "enabled", "budget_tokens": 2048}, "high": {"type": "enabled", "budget_tokens": 8192}}[effort]


def openai_reasoning(effort: str) -> Dict[str, str]:
    """OpenAI reasoning models (Responses API): reasoning={"effort": "low" | "medium" | "high"}."""
    return {"effort": effort}
