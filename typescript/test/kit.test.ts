// node --test --experimental-strip-types test/*.test.ts   (Node 22.18+; no API key, no network)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { StopPolicy, cacheLatestTurn, cachedSystem, callCost, pickEffort, pruneToolResults, runToolUses, selectTools, stripPrivateKeys, trimOutput } from "../src/index.ts";

const LOG = readFileSync(new URL("../../benchmark/sample-test.log", import.meta.url), "utf8");

test("cache: system block marked, rolling breakpoint moves", () => {
  assert.deepEqual(cachedSystem("x")[0].cache_control, { type: "ephemeral" });
  const m: any[] = [{ role: "user", content: [{ type: "text", text: "a", cache_control: { type: "ephemeral" } }] }, { role: "assistant", content: "ok" }, { role: "user", content: "b" }];
  const out: any[] = cacheLatestTurn(m);
  assert.equal(out[0].content[0].cache_control, undefined);
  assert.ok(out[2].content[0].cache_control);
  assert.ok(m[0].content[0].cache_control, "input untouched");
});

test("trim: the real 1,995-line log keeps the failure", () => {
  const out = trimOutput(LOG);
  assert.ok(out.split("\n").length < 80);
  assert.match(out, /refresh token keeps its scope/);
  assert.match(out, /'read write'/);
});

test("prune: waits for the batch, then summarises all but the last 3", () => {
  const conv: any[] = [{ role: "user", content: "task" }];
  for (let i = 0; i < 6; i++) {
    conv.push({ role: "assistant", content: [{ type: "tool_use", id: `t${i}`, name: "read_file", input: {} }] });
    conv.push({ role: "user", content: [{ type: "tool_result", tool_use_id: `t${i}`, content: `result ${i}\n` + "x".repeat(500) }] });
  }
  assert.equal(pruneToolResults(conv.slice(0, 11)).pruned, 0);
  const { messages, pruned } = pruneToolResults(conv);
  assert.equal(pruned, 3);
  assert.match(JSON.stringify(messages), /\[summary of an earlier result\] result 0/);
  assert.equal(pruneToolResults(messages).pruned, 0);
  assert.doesNotMatch(JSON.stringify(stripPrivateKeys(messages)), /_summary/);
});

test("parallel: one user message, original order, errors reported", async () => {
  const slow = async ({ x }: any) => { await new Promise((r) => setTimeout(r, 30)); return `slow ${x}`; };
  const msg: any = await runToolUses([{ id: "a", name: "slow", input: { x: 1 } }, { id: "b", name: "fast", input: { x: 2 } }, { id: "c", name: "nope", input: {} }],
    { slow, fast: ({ x }: any) => `fast ${x}` });
  assert.deepEqual(msg.content.map((b: any) => b.tool_use_id), ["a", "b", "c"]);
  assert.equal(msg.content[0].content, "slow 1");
  assert.equal(msg.content[2].is_error, true);
});

test("stop: done check, loop guard", () => {
  assert.ok(new StopPolicy({ doneCheck: () => true }).shouldStop());
  const p = new StopPolicy(); for (let i = 0; i < 3; i++) p.recordTool("run_tests", {});
  assert.ok(p.shouldStop()); assert.match(p.reason, /loop/);
});

test("tools: keeps the relevant ones", () => {
  const tools = [{ name: "run_tests", description: "Run the test suite" }, { name: "read_file", description: "Read a file" },
    { name: "slack_post", description: "Post a Slack message" }, { name: "grep", description: "Search files for a pattern" }];
  const names = selectTools(tools, "the failing test: search the files", 2, ["read_file"]).map((t) => t.name);
  assert.ok(names.includes("run_tests") && names.includes("read_file") && !names.includes("slack_post"));
});

test("effort and pricing", () => {
  assert.equal(pickEffort("Extract the email from this message"), "low");
  assert.equal(pickEffort("Debug the race condition"), "high");
  assert.ok(Math.abs(callCost({ input_tokens: 1e6, output_tokens: 1e5, cache_read_input_tokens: 1e6 }) - 3.2) < 1e-9);
});
