"""Price one agent run call by call, with any mix of the seven fixes. No API key needed.

Each call re-sends: system prompt + tool definitions + task + every earlier call's text and tool results.
Caching is simulated honestly: a call reads from cache only the prefix it shares with the previous call, so pruning
(which edits old history) breaks the cache from the edit onwards. That is why the kit prunes in batches.
Same model as the @tirthaexe infographic "7 ways to make your AI agents cheaper".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass
class Run:
    p_in: float = 2.0            # $ per million input tokens
    p_out: float = 10.0          # $ per million output tokens (thinking is billed as output)
    cache_read_x: float = 0.10
    cache_write_x: float = 1.25
    system: int = 3000           # system prompt tokens
    tool_schema: int = 500       # tokens per tool definition
    tools: int = 30              # tools sent every call
    tools_needed: int = 6        # tools left after filtering
    task: int = 1000
    tool_calls: int = 19         # one tool per call, then a final answer
    result: int = 4000           # tokens per tool result
    result_trimmed: int = 1000
    call_text: int = 300         # visible output per call, kept in history
    think: int = 1500
    think_low: int = 400
    keep_last: int = 3
    prune_at: int = 6
    summary: int = 150
    verify_tail: int = 3         # tool calls made after the check already passed
    parallel_groups: List[int] = field(default_factory=lambda: [3, 3, 3, 2])


FIXES = ("cache", "trim", "prune", "parallel", "stop", "tools", "effort")


def simulate(r: Run = Run(), cache=False, trim=False, prune=False, parallel=False, stop=False, tools=False, effort=False) -> Dict:
    n_tools = r.tool_calls - (r.verify_tail if stop else 0)
    if parallel:
        groups, left = [], n_tools
        for g in r.parallel_groups:
            take = min(g, left)
            if take:
                groups.append(take)
            left -= take
        groups += [1] * left
    else:
        groups = [1] * n_tools
    calls = len(groups) + 1
    prefix = [("sys", r.system), ("tools", r.tool_schema * (r.tools_needed if tools else r.tools)), ("task", r.task)]
    hist: List[list] = []
    prev: List[str] = []
    cost, per_call, tin, tout, rid = 0.0, [], 0, 0, 0
    for c in range(calls):
        ctx = prefix + [(h[0], h[1]) for h in hist]
        ids, toks = [b[0] for b in ctx], [b[1] for b in ctx]
        total = sum(toks)
        if cache:
            common = 0
            for a, b in zip(ids, prev):
                if a != b:
                    break
                common += 1
            read = sum(toks[:common])
            cin = read * r.p_in * r.cache_read_x + (total - read) * r.p_in * r.cache_write_x
        else:
            cin = total * r.p_in
        out = r.call_text + (r.think_low if effort else r.think)
        cc = (cin + out * r.p_out) / 1e6
        cost += cc; per_call.append(round(cc, 4)); tin += total; tout += out; prev = ids
        if c < calls - 1:
            hist.append([f"call{c}", r.call_text, "text"])
            for _ in range(groups[c]):
                hist.append([f"r{rid}", r.result_trimmed if trim else r.result, "result"]); rid += 1
            if prune:
                full = [h for h in hist if h[2] == "result"]
                if len(full) >= r.prune_at:
                    for h in full[:-r.keep_last]:
                        h[0] += "s"; h[1] = r.summary; h[2] = "summary"
    return dict(cost=round(cost, 4), calls=calls, tokens_in=tin, tokens_out=tout, per_call=per_call)


def report(r: Run = Run()) -> List[Dict]:
    base = simulate(r)
    rows = [dict(name="baseline", **base, saving=0.0)]
    for f in FIXES:
        x = simulate(r, **{f: True})
        rows.append(dict(name=f + " alone", **x, saving=round(1 - x["cost"] / base["cost"], 3)))
    x = simulate(r, **{f: True for f in FIXES})
    rows.append(dict(name="all seven", **x, saving=round(1 - x["cost"] / base["cost"], 3)))
    return rows


if __name__ == "__main__":
    for row in report():
        print(f"{row['name']:16s} ${row['cost']:.3f}  {row['calls']:2d} calls  -{row['saving'] * 100:4.0f}%")
