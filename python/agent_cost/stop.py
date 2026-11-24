"""Fix 5 - Know when to stop the agent.

Most wasted calls come after the work is done: re-running the same check, re-reading the same file. End the run when
a cheap, deterministic check passes, and guard against loops and runaway budgets.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class StopPolicy:
    done_check: Optional[Callable[[], bool]] = None   # e.g. lambda: run(["npm", "test"]).returncode == 0
    max_calls: int = 30                               # hard ceiling on model calls
    max_usd: float = 1.00                             # budget per run
    max_repeats: int = 2                              # the same tool call with the same input, this many times = a loop
    calls: int = 0
    spent: float = 0.0
    seen: Dict[str, int] = field(default_factory=dict)
    reason: str = ""

    def record_call(self, usd: float) -> None:
        self.calls += 1
        self.spent += usd

    def record_tool(self, name: str, args: dict) -> None:
        key = name + json.dumps(args, sort_keys=True, default=str)
        self.seen[key] = self.seen.get(key, 0) + 1

    def should_stop(self, after_tools: bool = True) -> bool:
        """Call after each round of tool results. True = end the run now (self.reason says why)."""
        if self.done_check and after_tools and self.done_check():
            self.reason = "done: the check passed"
        elif self.calls >= self.max_calls:
            self.reason = f"limit: {self.calls} calls"
        elif self.spent >= self.max_usd:
            self.reason = f"budget: ${self.spent:.2f}"
        elif any(v >= self.max_repeats + 1 for v in self.seen.values()):
            self.reason = "loop: the same tool call repeated"
        else:
            return False
        return True


def stop_hint() -> str:
    """One line for the system prompt so the model ends on its own too."""
    return ("When the task's check passes (tests green, file written, answer found), reply with the result and stop. "
            "Do not re-run a check that already passed.")
