"""A real coding agent with all seven fixes switchable, so you can see each one on your own bill.

    pip install anthropic            # Python 3.9+
    export ANTHROPIC_API_KEY=...
    python examples/agent_loop.py ../benchmark/fixture/billing "Make the failing test pass."

Every fix is a flag in Config. The benchmark (../benchmark/bench.py) runs the same task with all flags off, then on.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from agent_cost import (StopPolicy, anthropic_thinking, cache_latest_turn, cached_system, call_cost, pick_effort,  # noqa: E402
                        prune_tool_results, run_tool_uses, select_tools, stop_hint, strip_private_keys, trim_output)

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")


@dataclass
class Config:
    cache: bool = True      # 1 cache the stable prefix
    trim: bool = True       # 2 trim tool output
    prune: bool = True      # 3 summarise old results in batches
    parallel: bool = True   # 4 let the model call tools in parallel
    stop: bool = True       # 5 stop when the check passes
    tools: bool = True      # 6 send only the tools this step needs
    effort: bool = True     # 7 effort from the task (off = always high)
    extra_tools: int = 30   # unrelated tools a bloated agent carries (fix 6 drops them)
    max_calls: int = 40


SYSTEM = ("You are a careful coding agent working in a small repository. Use the tools to inspect files, run the tests, "
          "and edit code. Make the smallest correct fix.")


def make_tools(repo: pathlib.Path):
    def run_tests() -> str:
        p = subprocess.run(["node", "--test", "--test-reporter=spec"], cwd=repo, capture_output=True, text=True, timeout=120)
        return (p.stdout + p.stderr) + f"\n[exit code {p.returncode}]"

    def read_file(path: str) -> str:
        return (repo / path).read_text()

    def write_file(path: str, content: str) -> str:
        (repo / path).write_text(content)
        return f"wrote {len(content)} chars to {path}"

    def grep(pattern: str, path: str = ".") -> str:
        p = subprocess.run(["grep", "-rn", "--exclude-dir=node_modules", pattern, path], cwd=repo, capture_output=True, text=True)
        return p.stdout or "(no matches)"

    def list_files() -> str:
        return "\n".join(str(p.relative_to(repo)) for p in sorted(repo.rglob("*")) if p.is_file() and "node_modules" not in p.parts)

    handlers = dict(run_tests=run_tests, read_file=read_file, write_file=write_file, grep=grep, list_files=list_files)
    s = lambda **props: {"type": "object", "properties": {k: {"type": "string", "description": v} for k, v in props.items()}, "required": list(props)}
    defs = [
        {"name": "run_tests", "description": "Run the project's test suite and return its output.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "read_file", "description": "Read a file in the repository.", "input_schema": s(path="Path relative to the repo root")},
        {"name": "write_file", "description": "Replace a file's contents in the repository.", "input_schema": s(path="Path relative to the repo root", content="New file contents")},
        {"name": "grep", "description": "Search the repository for a regex pattern; returns file:line:text.", "input_schema": s(pattern="Regular expression")},
        {"name": "list_files", "description": "List every file in the repository.", "input_schema": {"type": "object", "properties": {}}},
    ]
    return handlers, defs


def bloat(n: int) -> List[Dict[str, Any]]:
    """Unrelated integrations a 'kitchen sink' agent carries: realistic size, never needed for this task."""
    apps = ["jira", "slack", "notion", "gmail", "linear", "stripe", "hubspot", "zendesk", "figma", "drive", "sheets", "calendar",
            "salesforce", "intercom", "asana", "trello", "airtable", "shopify", "twilio", "sentry", "datadog", "pagerduty", "confluence",
            "dropbox", "zoom", "mailchimp", "discord", "postgres", "bigquery", "snowflake"]
    out = []
    for i in range(n):
        app = apps[i % len(apps)]
        props = {f"{app}_{k}": {"type": "string", "description": f"The {k.replace('_', ' ')} for the {app} request. " * 3}
                 for k in ("workspace_id", "object_id", "title", "body", "assignee", "labels", "priority", "due_date")}
        out.append({"name": f"{app}_action_{i}", "description": f"Create, update or search {app} records for the user. " * 6,
                    "input_schema": {"type": "object", "properties": props, "required": [f"{app}_object_id"]}})
    return out


def run_agent(repo: str, task: str, cfg: Config = Config(), verbose: bool = True) -> Dict[str, Any]:
    import anthropic
    client = anthropic.Anthropic()
    repo_p = pathlib.Path(repo).resolve()
    handlers, core = make_tools(repo_p)
    all_tools = core + bloat(cfg.extra_tools)
    tools = select_tools(all_tools, task + " tests files code", k=5, always=["run_tests", "read_file", "write_file"]) if cfg.tools else all_tools
    effort = pick_effort(task) if cfg.effort else "high"
    thinking = anthropic_thinking(effort)
    system = SYSTEM + (" " + stop_hint() if cfg.stop else "")
    system_param = cached_system(system) if cfg.cache else system
    tool_choice = {"type": "auto"} if cfg.parallel else {"type": "auto", "disable_parallel_tool_use": True}
    done = lambda: subprocess.run(["node", "--test"], cwd=repo_p, capture_output=True).returncode == 0
    policy = StopPolicy(done_check=done if cfg.stop else None, max_calls=cfg.max_calls, max_usd=5.0)
    post = (lambda t: trim_output(t)) if cfg.trim else (lambda t: t)

    messages: List[Dict[str, Any]] = [{"role": "user", "content": task}]
    calls: List[Dict[str, Any]] = []
    while True:
        if cfg.prune:
            messages, _ = prune_tool_results(messages, keep_last=3, prune_at=6)
        send = strip_private_keys(messages)
        if cfg.cache:
            send = cache_latest_turn(send)
        kw = dict(model=MODEL, max_tokens=12000 if thinking else 4000, system=system_param, tools=tools, tool_choice=tool_choice, messages=send)
        if thinking:
            kw["thinking"] = thinking
        resp = client.messages.create(**kw)
        usd = call_cost(resp.usage)
        policy.record_call(usd)
        u = resp.usage
        calls.append(dict(input=u.input_tokens, cache_read=u.cache_read_input_tokens or 0, cache_write=u.cache_creation_input_tokens or 0,
                          output=u.output_tokens, usd=round(usd, 5)))
        if verbose:
            print(f"call {len(calls):2d}  in {u.input_tokens:6d}  cache r/w {calls[-1]['cache_read']:6d}/{calls[-1]['cache_write']:6d}  out {u.output_tokens:5d}  ${usd:.4f}")
        messages.append({"role": "assistant", "content": resp.content})
        uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not uses:
            reason = "model finished"
            break
        for b in uses:
            policy.record_tool(b.name, b.input)
        messages.append(asyncio.run(run_tool_uses(uses, handlers, postprocess=post)))
        if policy.should_stop():
            reason = policy.reason
            break
    total = sum(c["usd"] for c in calls)
    return dict(calls=calls, usd=round(total, 4), n_calls=len(calls), reason=reason, tests_pass=done(), tools_sent=len(tools), effort=effort)


if __name__ == "__main__":
    repo, task = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "Make the failing test pass.")
    print(json.dumps({k: v for k, v in run_agent(repo, task).items() if k != "calls"}, indent=1))
