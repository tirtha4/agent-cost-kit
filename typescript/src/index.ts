// AI Agent Cost Kit (@tirthaexe): seven ways to cut an agent's API bill without changing models.
// Same functions as the Python package; see the comments in each file.
type Block = Record<string, any>;
type Msg = { role: "user" | "assistant"; content: string | Block[] };
const clone = <T>(x: T): T => structuredClone(x);

// ---------- 1 cache the stable prefix (tools -> system -> messages) ----------
export function cachedSystem(text: string, ttl?: "5m" | "1h"): Block[] {
  return [{ type: "text", text, cache_control: { type: "ephemeral", ...(ttl ? { ttl } : {}) } }];
}
export function cacheTools(tools: Block[]): Block[] {
  const out = clone(tools);
  if (out.length) out[out.length - 1].cache_control = { type: "ephemeral" };
  return out;
}
/** Rolling breakpoint on the newest turn; clears older rolling marks (max 4 breakpoints per request). */
export function cacheLatestTurn(messages: Msg[]): Msg[] {
  const out = messages.map((m) => ({ ...m, content: Array.isArray(m.content) ? m.content.map((b) => ({ ...b })) : m.content }));
  for (const m of out) if (Array.isArray(m.content)) for (const b of m.content) delete b.cache_control;
  const last = out[out.length - 1];
  if (last) {
    if (typeof last.content === "string") last.content = [{ type: "text", text: last.content }];
    (last.content as Block[])[(last.content as Block[]).length - 1].cache_control = { type: "ephemeral" };
  }
  return out;
}
export function cacheReport(u: Block) {
  const read = u.cache_read_input_tokens ?? 0, write = u.cache_creation_input_tokens ?? 0, fresh = u.input_tokens ?? 0;
  const total = read + write + fresh;
  return { cacheRead: read, cacheWrite: write, uncached: fresh, hitRatio: total ? Math.round((read / total) * 1000) / 1000 : 0 };
}

// ---------- 2 send the lines that matter ----------
const PATTERNS = /\berror\b|\bfail(ed|ure|ing)?\b|\bexception\b|traceback|\bpanic\b|✖|assert|\bwarn(ing)?\b/i;
export const estimateTokens = (s: string) => (s ? Math.max(1, Math.floor(s.length / 4)) : 0);
export function trimOutput(text: string, o: { maxLines?: number; pattern?: RegExp; before?: number; after?: number; head?: number; tail?: number; maxWindows?: number } = {}): string {
  const { maxLines = 80, pattern = PATTERNS, before = 3, after = 16, head = 10, tail = 20, maxWindows = 4 } = o;
  const lines = text.split("\n"), n = lines.length;
  if (n <= maxLines) return text;
  const hits = lines.flatMap((l, i) => (pattern.test(l) ? [i] : []));
  let spans: [number, number][] = [];
  if (hits.length) {
    for (const h of hits) {
      const a = Math.max(0, h - before), b = Math.min(n, h + after + 1), last = spans[spans.length - 1];
      if (last && a <= last[1]) last[1] = Math.max(last[1], b); else spans.push([a, b]);
    }
    spans = spans.slice(0, maxWindows);
  } else spans = [[0, Math.min(head, n)], [Math.max(0, n - tail), n]];
  const kept: string[] = [];
  for (const [a, b] of spans) { if (kept.length) kept.push("…"); for (let i = a; i < b; i++) kept.push(`${i + 1}: ${lines[i]}`); }
  const shown = spans.reduce((s, [a, b]) => s + b - a, 0);
  return `[trimmed: showing ${shown} of ${n} lines${hits.length ? ` around ${hits.length} matches` : ", head and tail"}; ask for a line range if you need more]\n` + kept.join("\n");
}
export function capTokens(text: string, maxTokens = 2000): string {
  if (estimateTokens(text) <= maxTokens) return text;
  const keep = (maxTokens * 4) / 2;
  return text.slice(0, keep) + `\n…[${estimateTokens(text) - maxTokens} tokens cut]…\n` + text.slice(-keep);
}

// ---------- 3 summarise old results, in batches (so the cache survives) ----------
export const firstLinesSummary = (t: string, max = 300) => { const b = t.split("\n").map((l) => l.trim()).filter(Boolean).join(" "); return b.length > max ? b.slice(0, max) + "…" : b; };
const resultBlocks = (ms: Msg[]) => ms.flatMap((m) => (m.role === "user" && Array.isArray(m.content) ? m.content.filter((b) => b.type === "tool_result") : []));
const blockText = (b: Block) => (Array.isArray(b.content) ? b.content.filter((x: Block) => x.type === "text").map((x: Block) => x.text).join("\n") : String(b.content ?? ""));
export function pruneToolResults(messages: Msg[], keepLast = 3, pruneAt = 6, summarize = firstLinesSummary): { messages: Msg[]; pruned: number } {
  const out = clone(messages);
  const full = resultBlocks(out).filter((b) => !b._summary);
  if (full.length < pruneAt) return { messages: out, pruned: 0 };
  const old = keepLast ? full.slice(0, -keepLast) : full;
  for (const b of old) { b.content = "[summary of an earlier result] " + summarize(blockText(b)); b._summary = true; }
  return { messages: out, pruned: old.length };
}
export function stripPrivateKeys(messages: Msg[]): Msg[] {
  const out = clone(messages);
  for (const b of resultBlocks(out)) delete b._summary;
  return out;
}

// ---------- 4 run independent tools at once, one user message back ----------
export async function runToolUses(uses: { id: string; name: string; input: any }[], handlers: Record<string, (args: any) => any>,
                                  postprocess: (s: string) => string = (s) => s): Promise<Msg> {
  const content = await Promise.all(uses.map(async (u) => {
    try {
      if (!handlers[u.name]) throw new Error(`unknown tool ${u.name}`);
      const r = await handlers[u.name](u.input ?? {});
      return { type: "tool_result", tool_use_id: u.id, content: postprocess(typeof r === "string" ? r : JSON.stringify(r)) };
    } catch (e: any) {
      return { type: "tool_result", tool_use_id: u.id, content: `${e?.name ?? "Error"}: ${e?.message ?? e}`, is_error: true };
    }
  }));
  return { role: "user", content };
}

// ---------- 5 stop when the check passes ----------
export class StopPolicy {
  calls = 0; spent = 0; reason = ""; seen = new Map<string, number>();
  o: { doneCheck?: () => boolean; maxCalls?: number; maxUsd?: number; maxRepeats?: number };
  constructor(o: { doneCheck?: () => boolean; maxCalls?: number; maxUsd?: number; maxRepeats?: number } = {}) { this.o = o; }
  recordCall(usd: number) { this.calls++; this.spent += usd; }
  recordTool(name: string, args: unknown) { const k = name + JSON.stringify(args); this.seen.set(k, (this.seen.get(k) ?? 0) + 1); }
  shouldStop(): boolean {
    const { doneCheck, maxCalls = 30, maxUsd = 1, maxRepeats = 2 } = this.o;
    if (doneCheck?.()) this.reason = "done: the check passed";
    else if (this.calls >= maxCalls) this.reason = `limit: ${this.calls} calls`;
    else if (this.spent >= maxUsd) this.reason = `budget: $${this.spent.toFixed(2)}`;
    else if ([...this.seen.values()].some((v) => v >= maxRepeats + 1)) this.reason = "loop: the same tool call repeated";
    else return false;
    return true;
  }
}
export const stopHint = () => "When the task's check passes (tests green, file written, answer found), reply with the result and stop. Do not re-run a check that already passed.";

// ---------- 6 only the tools this step needs ----------
const STOP = new Set("the a an to of and or in on for with this that it is be use when from by as".split(" "));
const words = (s: string) => new Set((s.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((w) => w.length > 2 && !STOP.has(w)));
export const toolTokens = (tools: Block[]) => estimateTokens(JSON.stringify(tools));
export function selectTools(tools: Block[], step: string, k = 5, always: string[] = []): Block[] {
  const want = words(step);
  const scored = tools.filter((t) => !always.includes(t.name))
    .map((t) => ({ t, s: [...words(t.name.replaceAll("_", " ") + " " + (t.description ?? ""))].filter((w) => want.has(w)).length }))
    .filter((x) => x.s > 0).sort((a, b) => b.s - a.s || a.t.name.localeCompare(b.t.name)).slice(0, k);
  const keep = new Set([...always, ...scored.map((x) => x.t.name)]);
  return tools.filter((t) => keep.has(t.name));
}

// ---------- 7 effort to match the task ----------
export type Effort = "low" | "medium" | "high";
export function pickEffort(task: string): Effort {
  const t = task.toLowerCase();
  if (/\b(debug|refactor|architect\w*|design|plan|prove|migrat\w*|optimi[sz]e|security|review|root cause|race condition)\b/.test(t)) return "high";
  if (/\b(extract|classif\w*|sort|tag|label|route|format|rename|translate|lookup|look up|search|find|list|count|convert)\b/.test(t)) return "low";
  return "medium";
}
/** Claude extended thinking per effort (undefined = don't send `thinking`). budget_tokens must stay below max_tokens. */
export const anthropicThinking = (e: Effort) => ({ low: undefined, medium: { type: "enabled", budget_tokens: 2048 }, high: { type: "enabled", budget_tokens: 8192 } } as const)[e];
/** OpenAI reasoning models (Responses API): reasoning: { effort } */
export const openaiReasoning = (e: Effort) => ({ effort: e });

// ---------- pricing ($ per million tokens: check the provider's page) ----------
export const SONNET = { input: 2, output: 10, cacheReadX: 0.1, cacheWriteX: 1.25 };
export function callCost(u: Block, p = SONNET): number {
  return ((u.input_tokens ?? 0) * p.input + (u.cache_read_input_tokens ?? 0) * p.input * p.cacheReadX
    + (u.cache_creation_input_tokens ?? 0) * p.input * p.cacheWriteX + (u.output_tokens ?? 0) * p.output) / 1e6;
}
