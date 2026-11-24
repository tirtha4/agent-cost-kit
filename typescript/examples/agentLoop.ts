// A real coding agent with all seven fixes on (same as python/examples/agent_loop.py).
//   npm install && export ANTHROPIC_API_KEY=...
//   node --experimental-strip-types examples/agentLoop.ts ../benchmark/fixture/billing "Make the failing test pass."
import Anthropic from "@anthropic-ai/sdk";
import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { StopPolicy, anthropicThinking, cacheLatestTurn, cachedSystem, callCost, pickEffort, pruneToolResults, runToolUses, selectTools,
  stopHint, stripPrivateKeys, trimOutput } from "../src/index.ts";

const MODEL = process.env.AGENT_MODEL ?? "claude-sonnet-5-5";
const [repoArg, taskArg] = process.argv.slice(2);
const repo = resolve(repoArg ?? "../benchmark/fixture/billing");
const task = taskArg ?? "Make the failing test pass.";

const runTests = () => { const p = spawnSync("node", ["--test", "--test-reporter=spec"], { cwd: repo, encoding: "utf8" }); return `${p.stdout}${p.stderr}\n[exit code ${p.status}]`; };
const walk = (d: string): string[] => readdirSync(d).flatMap((f) => { const p = join(d, f); return f === "node_modules" ? [] : statSync(p).isDirectory() ? walk(p) : [relative(repo, p)]; });
const handlers: Record<string, (a: any) => string> = {
  run_tests: () => runTests(),
  read_file: ({ path }) => readFileSync(join(repo, path), "utf8"),
  write_file: ({ path, content }) => { writeFileSync(join(repo, path), content); return `wrote ${content.length} chars to ${path}`; },
  grep: ({ pattern }) => { try { return execFileSync("grep", ["-rn", "--exclude-dir=node_modules", pattern, "."], { cwd: repo, encoding: "utf8" }); } catch { return "(no matches)"; } },
  list_files: () => walk(repo).join("\n"),
};
const str = (props: Record<string, string>) => ({ type: "object", properties: Object.fromEntries(Object.entries(props).map(([k, d]) => [k, { type: "string", description: d }])), required: Object.keys(props) });
const ALL_TOOLS: any[] = [
  { name: "run_tests", description: "Run the project's test suite and return its output.", input_schema: { type: "object", properties: {} } },
  { name: "read_file", description: "Read a file in the repository.", input_schema: str({ path: "Path relative to the repo root" }) },
  { name: "write_file", description: "Replace a file's contents in the repository.", input_schema: str({ path: "Path relative to the repo root", content: "New file contents" }) },
  { name: "grep", description: "Search the repository for a regex pattern; returns file:line:text.", input_schema: str({ pattern: "Regular expression" }) },
  { name: "list_files", description: "List every file in the repository.", input_schema: { type: "object", properties: {} } },
  // ...plus whatever unrelated integrations your agent carries: fix 6 keeps them out of this task's requests
];

const client = new Anthropic();
const tools = selectTools(ALL_TOOLS, task + " tests files code", 5, ["run_tests", "read_file", "write_file"]);   // 6
const effort = pickEffort(task), thinking = anthropicThinking(effort);                                          // 7
const system = cachedSystem("You are a careful coding agent working in a small repository. Use the tools to inspect files, run the tests, and edit code. Make the smallest correct fix. " + stopHint()); // 1 + 5
const policy = new StopPolicy({ doneCheck: () => spawnSync("node", ["--test"], { cwd: repo }).status === 0, maxCalls: 40, maxUsd: 5 });          // 5

let messages: any[] = [{ role: "user", content: task }];
let total = 0;
for (;;) {
  messages = pruneToolResults(messages, 3, 6).messages;                                                         // 3
  const resp = await client.messages.create({
    model: MODEL, max_tokens: thinking ? 12000 : 4000, system, tools, tool_choice: { type: "auto" },          // 4: parallel tool use stays on
    messages: cacheLatestTurn(stripPrivateKeys(messages)),                                                      // 1: rolling breakpoint
    ...(thinking ? { thinking } : {}),
  } as any);
  const usd = callCost(resp.usage); total += usd; policy.recordCall(usd);
  console.log(`call ${policy.calls}  in ${resp.usage.input_tokens}  cache read ${resp.usage.cache_read_input_tokens ?? 0}  out ${resp.usage.output_tokens}  $${usd.toFixed(4)}`);
  messages.push({ role: "assistant", content: resp.content });
  const uses = resp.content.filter((b: any) => b.type === "tool_use") as any[];
  if (resp.stop_reason !== "tool_use" || !uses.length) { console.log("model finished"); break; }
  uses.forEach((u) => policy.recordTool(u.name, u.input));
  messages.push(await runToolUses(uses, handlers, (t) => trimOutput(t)));                                      // 4 + 2
  if (policy.shouldStop()) { console.log(policy.reason); break; }
}
console.log(`total $${total.toFixed(4)} over ${policy.calls} calls`);
