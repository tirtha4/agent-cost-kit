# AI Agent Cost Kit

**Seven ways to cut your AI agent's API bill without changing models.** Python and TypeScript code for each fix, a bill calculator, and a benchmark that measures the savings on a real bug.

An agent re-sends its whole context on every call: the system prompt, the tool definitions, the task, and everything it has read so far. In a typical 20-call coding run:
- **55%** of the bill is old tool results riding along again;
- **22%** is tool definitions;
- **11%** is thinking;
- the answer you actually read is **2%**.

These fixes go after the re-sent tokens. In the kit's modelled run, the bill drops from **$2.75 to $0.17** with all seven.

| # | Fix | What it does | Saves alone* | Code |
|---|---|---|---|---|
| 1 | Cache the prefix | Stable parts first (tools, system), marked once; later calls read them at 10% of the input price | −70% | [`cache.py`](python/agent_cost/cache.py) |
| 2 | Trim tool results | Send the 20 lines around the error, not the 2,000-line log | −41% | [`trim.py`](python/agent_cost/trim.py) |
| 3 | Prune old results | Summarise all but the last 3 results, **in batches** so the cache survives | −34% | [`context.py`](python/agent_cost/context.py) |
| 4 | Parallel tools | Independent reads in one turn: fewer round trips, so the context is re-sent fewer times | −27% | [`parallel.py`](python/agent_cost/parallel.py) |
| 5 | Stop on a check | End the run when a cheap check passes; guard against loops and runaway budgets | −23% | [`stop.py`](python/agent_cost/stop.py) |
| 6 | Filter the tools | Only send the tools this step needs: every definition costs tokens on every call | −17% | [`tools.py`](python/agent_cost/tools.py) |
| 7 | Lower the effort | No heavy reasoning for extraction, sorting or lookups | −8% | [`effort.py`](python/agent_cost/effort.py) |

\*In the modelled 20-call run. The savings overlap, so they don't add up. Measure your own agent with the [benchmark](#measure-your-own-agent).

The TypeScript versions of all seven are in [`typescript/src/index.ts`](typescript/src/index.ts).

## What's inside
```
python/agent_cost/     the seven fixes, plus pricing.py (cost per call) and simulate.py (the cost model)
python/examples/       agent_loop.py: a real coding agent with every fix as a switch
python/tests/          19 tests (no API key needed)
typescript/src/        the same seven fixes in TypeScript (index.ts)
typescript/examples/   agentLoop.ts
typescript/test/       7 tests (no API key needed)
benchmark/             bench.py: the cost model, or --live before/after on a real bug (fixture/billing)
calculator/            index.html (open it in a browser) and agent-cost-calculator.xlsx (Excel or Google Sheets)
```

## Quick start
```bash
git clone https://github.com/tirtha4/agent-cost-kit && cd agent-cost-kit

# Python 3.9+
python -m unittest discover -s python/tests          # tests, no key needed
python benchmark/bench.py                            # the cost model: baseline vs each fix vs all seven
pip install -e ".[examples]"                         # the package + the Anthropic SDK for the examples

# TypeScript (Node 22.18+)
cd typescript && npm install && npm test
```

## Use it in your agent (Python)
```python
import asyncio
from agent_cost import (cached_system, cache_latest_turn, trim_output, prune_tool_results, strip_private_keys,
                        run_tool_uses, StopPolicy, select_tools, pick_effort, anthropic_thinking)

tools  = select_tools(ALL_TOOLS, task, k=5, always=["read_file"])               # 6
system = cached_system(SYSTEM_PROMPT)                                            # 1 (also caches the tools before it)
effort = pick_effort(task); thinking = anthropic_thinking(effort)                # 7
policy = StopPolicy(done_check=lambda: tests_pass(), max_calls=30, max_usd=1.0)  # 5

extra = {"thinking": thinking} if thinking else {}
while True:
    messages, _ = prune_tool_results(messages, keep_last=3, prune_at=6)          # 3 (batched)
    resp = client.messages.create(model=MODEL, max_tokens=12000 if thinking else 4000, system=system, tools=tools,
                                  messages=cache_latest_turn(strip_private_keys(messages)), **extra)
    messages.append({"role": "assistant", "content": resp.content})
    uses = [b for b in resp.content if b.type == "tool_use"]
    if not uses: break
    for u in uses: policy.record_tool(u.name, u.input)
    messages.append(asyncio.run(run_tool_uses(uses, HANDLERS, postprocess=trim_output)))  # 4 + 2
    if policy.should_stop(): break
```
The full, runnable version is [`python/examples/agent_loop.py`](python/examples/agent_loop.py). It's a real coding agent with every fix as an on/off switch, so you can see each one on your own bill.

## Measure your own agent
```bash
python benchmark/bench.py               # offline: the call-by-call cost model, no key, no cost
python benchmark/bench.py --live        # real: the same bug fixed twice on the API (all fixes off, then on)
python benchmark/bench.py --live --each # real: also each fix on its own (8 runs)
```
The live task is a real bug: [`benchmark/fixture/billing`](benchmark/fixture/billing) has 1,960 passing tests and one failing one. A live pair costs a few cents to about $1 at list prices. To log your own agent instead, record `call_cost(resp.usage)` and `cache_report(resp.usage)` for every call ([`pricing.py`](python/agent_cost/pricing.py), [`cache.py`](python/agent_cost/cache.py)).

## The calculator
- [`calculator/agent-cost-calculator.xlsx`](calculator/agent-cost-calculator.xlsx): change the blue numbers to your agent's, switch each fix on (1) or off (0), and see the bill per run and per month. It works in Excel and Google Sheets.
- [`calculator/index.html`](calculator/index.html): the same calculator as a single web page. Open it in a browser.

Both run the same call-by-call model as [`simulate.py`](python/agent_cost/simulate.py).

## Notes
- **Prices** default to Claude Sonnet 5.5 list prices ($2 in / $10 out per million tokens; cache reads 0.1×, 5-minute writes 1.25×). Check your provider's pricing page; every price is a parameter.
- **Caching:** prompts below the model's minimum length (about 1,024 tokens on Sonnet/Opus) aren't cached. The default cache lives 5 minutes; pass `ttl="1h"` for slow loops.
- **Pruning vs caching:** editing old history re-writes the cache from that point on. Pruning on every call can cost more than it saves, so this kit prunes in batches.
- **Effort:** thinking tokens are billed as output. `anthropic_thinking()` sets a thinking budget; OpenAI reasoning models take `reasoning={"effort": "low"}`.

## License
MIT. Use it, fork it, ship it. Made by [@tirthaexe](https://www.instagram.com/tirthaexe/).
