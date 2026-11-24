"""python -m unittest discover -s python/tests   (no API key, no network)"""
import asyncio
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from agent_cost import (StopPolicy, anthropic_thinking, cache_latest_turn, cache_report, cached_system, call_cost, cap_tokens,
                        pick_effort, prune_tool_results, run_tool_uses, select_tools, strip_private_keys, tool_tokens, trim_output)
from agent_cost.simulate import Run, simulate

LOG = pathlib.Path(__file__).resolve().parents[2] / "benchmark" / "sample-test.log"


class Cache(unittest.TestCase):
    def test_system_block_is_marked(self):
        b = cached_system("You are an agent.")[0]
        self.assertEqual(b["cache_control"], {"type": "ephemeral"})
        self.assertEqual(cached_system("x", ttl="1h")[0]["cache_control"]["ttl"], "1h")

    def test_rolling_breakpoint_moves(self):
        m = [{"role": "user", "content": [{"type": "text", "text": "a", "cache_control": {"type": "ephemeral"}}]},
             {"role": "assistant", "content": "ok"}, {"role": "user", "content": "b"}]
        out = cache_latest_turn(m)
        self.assertNotIn("cache_control", out[0]["content"][0])
        self.assertIn("cache_control", out[-1]["content"][-1])
        self.assertIn("cache_control", m[0]["content"][0])          # input untouched

    def test_report(self):
        self.assertEqual(cache_report({"cache_read_input_tokens": 900, "input_tokens": 100})["hit_ratio"], 0.9)


class Trim(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(trim_output("a\nb"), "a\nb")

    def test_real_log_keeps_the_failure(self):
        text = LOG.read_text()
        out = trim_output(text)
        self.assertLess(len(out.splitlines()), 80)
        self.assertIn("refresh token keeps its scope", out)
        self.assertIn("'read write'", out)
        self.assertTrue(out.startswith("[trimmed: showing"))

    def test_no_match_keeps_head_and_tail(self):
        out = trim_output("\n".join(f"line {i}" for i in range(500)))
        self.assertIn("1: line 0", out); self.assertIn("500: line 499", out)

    def test_cap(self):
        self.assertLess(len(cap_tokens("x" * 40000, 1000)), 9000)


def _conv(n):
    m = [{"role": "user", "content": "task"}]
    for i in range(n):
        m.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "read_file", "input": {}}]})
        m.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": f"result {i}\n" + "x" * 500}]})
    return m


class Prune(unittest.TestCase):
    def test_waits_for_the_batch(self):
        _, n = prune_tool_results(_conv(5), keep_last=3, prune_at=6)
        self.assertEqual(n, 0)

    def test_batch_summarises_all_but_last(self):
        out, n = prune_tool_results(_conv(6), keep_last=3, prune_at=6)
        self.assertEqual(n, 3)
        res = [b for m in out if isinstance(m["content"], list) for b in m["content"] if b["type"] == "tool_result"]
        self.assertTrue(res[0]["content"].startswith("[summary"))
        self.assertTrue(res[-1]["content"].startswith("result 5"))
        out2, n2 = prune_tool_results(out, 3, 6)                    # next call: no new batch yet, nothing changes
        self.assertEqual(n2, 0)
        self.assertNotIn("_summary", str(strip_private_keys(out2)))


class Parallel(unittest.TestCase):
    def test_one_message_in_order(self):
        async def slow(x):
            await asyncio.sleep(0.05); return f"slow {x}"
        uses = [{"id": "a", "name": "slow", "input": {"x": 1}}, {"id": "b", "name": "fast", "input": {"x": 2}}, {"id": "c", "name": "nope", "input": {}}]
        msg = asyncio.run(run_tool_uses(uses, {"slow": slow, "fast": lambda x: f"fast {x}"}))
        self.assertEqual(msg["role"], "user")
        self.assertEqual([b["tool_use_id"] for b in msg["content"]], ["a", "b", "c"])
        self.assertEqual(msg["content"][0]["content"], "slow 1")
        self.assertTrue(msg["content"][2]["is_error"])


class Stop(unittest.TestCase):
    def test_done_check(self):
        p = StopPolicy(done_check=lambda: True)
        self.assertTrue(p.should_stop()); self.assertIn("done", p.reason)

    def test_loop(self):
        p = StopPolicy()
        for _ in range(3):
            p.record_tool("run_tests", {})
        self.assertTrue(p.should_stop()); self.assertIn("loop", p.reason)

    def test_budget(self):
        p = StopPolicy(max_usd=0.5); p.record_call(0.6)
        self.assertTrue(p.should_stop())


class Tools(unittest.TestCase):
    TOOLS = [{"name": "run_tests", "description": "Run the test suite"}, {"name": "read_file", "description": "Read a file"},
             {"name": "jira_create_issue", "description": "Create a Jira issue"}, {"name": "slack_post", "description": "Post a Slack message"},
             {"name": "grep", "description": "Search files for a pattern"}]

    def test_select(self):
        names = [t["name"] for t in select_tools(self.TOOLS, "the failing test: search the files", k=2, always=["read_file"])]
        self.assertIn("read_file", names); self.assertIn("run_tests", names); self.assertNotIn("slack_post", names)

    def test_tokens(self):
        self.assertGreater(tool_tokens(self.TOOLS), 20)


class Effort(unittest.TestCase):
    def test_routes(self):
        self.assertEqual(pick_effort("Extract the email from this message"), "low")
        self.assertEqual(pick_effort("Debug the race condition in the queue"), "high")
        self.assertEqual(pick_effort("Write a reply to this customer"), "medium")
        self.assertIsNone(anthropic_thinking("low"))


class Pricing(unittest.TestCase):
    def test_cost(self):
        c = call_cost({"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_read_input_tokens": 1_000_000})
        self.assertAlmostEqual(c, 2.0 + 1.0 + 0.2)


class Model(unittest.TestCase):
    def test_matches_the_infographic(self):
        self.assertAlmostEqual(simulate(Run())["cost"], 2.754, places=3)
        self.assertAlmostEqual(simulate(Run(), **{k: True for k in ("cache", "trim", "prune", "parallel", "stop", "tools", "effort")})["cost"], 0.171, delta=0.001)

    def test_pruning_every_call_would_break_the_cache(self):
        r = Run(prune_at=4, keep_last=3)                              # prunes on almost every call
        both = simulate(r, cache=True, prune=True)["cost"]; cache_only = simulate(r, cache=True)["cost"]
        self.assertGreater(both, cache_only * 0.9)                    # little or no gain on top of caching


if __name__ == "__main__":
    unittest.main()
