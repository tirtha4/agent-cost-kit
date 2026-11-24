"""Fix 4 - Run independent tools at once.

Claude can ask for several tools in one turn (several `tool_use` blocks). Run them together and send ALL the results
back in ONE user message: one round trip instead of three, so the context is re-sent once instead of three times.
(Parallel tool use is on by default; `tool_choice={"type": "auto", "disable_parallel_tool_use": True}` turns it off.)
"""
from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Awaitable, Callable, Dict, List, Union

Handler = Callable[..., Union[Any, Awaitable[Any]]]


async def _call(handler: Handler, args: Dict[str, Any]) -> Any:
    if inspect.iscoroutinefunction(handler):
        return await handler(**args)
    return await asyncio.to_thread(handler, **args)


async def run_tool_uses(tool_uses: List[Any], handlers: Dict[str, Handler], max_concurrency: int = 8,
                        postprocess: Callable[[str], str] = lambda s: s) -> Dict[str, Any]:
    """Run every tool_use block concurrently. Returns ONE user message holding every tool_result, in the original order."""
    sem = asyncio.Semaphore(max_concurrency)

    def field(b: Any, k: str) -> Any:
        return b[k] if isinstance(b, dict) else getattr(b, k)

    async def one(b: Any) -> Dict[str, Any]:
        name, args, tid = field(b, "name"), field(b, "input") or {}, field(b, "id")
        async with sem:
            try:
                if name not in handlers:
                    raise KeyError(f"unknown tool {name!r}")
                res = await _call(handlers[name], args)
                text = res if isinstance(res, str) else json.dumps(res, default=str)
                return {"type": "tool_result", "tool_use_id": tid, "content": postprocess(text)}
            except Exception as e:  # the model sees the error and can recover
                return {"type": "tool_result", "tool_use_id": tid, "content": f"{type(e).__name__}: {e}", "is_error": True}

    results = await asyncio.gather(*(one(b) for b in tool_uses))
    return {"role": "user", "content": list(results)}
