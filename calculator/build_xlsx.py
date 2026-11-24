"""Build agent-cost-calculator.xlsx: the same call-by-call model as python/agent_cost/simulate.py, in live formulas.
    python calculator/build_xlsx.py [out.xlsx] [switches like 1111111]
openpyxl writes formulas without cached values; open it in Excel or Google Sheets (or recalculate with LibreOffice) to see the numbers."""
import pathlib, sys
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

OUT = sys.argv[1] if len(sys.argv) > 1 else str(pathlib.Path(__file__).with_name("agent-cost-calculator.xlsx"))
SW = sys.argv[2] if len(sys.argv) > 2 else "1111111"
F = "Arial"
BLUE, BLACK, GREY = Font(name=F, color="0000FF"), Font(name=F), Font(name=F, color="6B675F", size=9)
BOLD, TITLE, H2 = Font(name=F, bold=True), Font(name=F, bold=True, size=18), Font(name=F, bold=True, size=11)
YEL = PatternFill("solid", fgColor="FFFF00"); SOFT = PatternFill("solid", fgColor="F6F5F1"); HI = PatternFill("solid", fgColor="FFD43B")
line = Border(bottom=Side(style="thin", color="E4E1DA"))
wb = Workbook(); wb.properties.creator = "tirthaexe"; wb.properties.title = "Agent Bill Calculator"; c = wb.active; c.title = "Calculator"; k = wb.create_sheet("Calls")

c["A1"] = "Agent Bill Calculator"; c["A1"].font = TITLE
c["A2"] = "@tirthaexe · AI Agent Cost Kit · what your agent costs per month, and what each fix saves"; c["A2"].font = GREY
c["A3"] = "How to use: change the blue numbers; switch fixes on (1) or off (0) in the yellow cells. Everything else is formulas."; c["A3"].font = Font(name=F, italic=True)

INPUTS = [  # row, label, value, note, number format
    (6, "Runs per day", 200, "How many times your agent runs a task each day", "#,##0"),
    (7, "Tool calls per run", 19, "One tool per call, then a final answer (max 59)", "0"),
    (8, "Tokens per tool result", 4000, "File reads, test logs, API responses", "#,##0"),
    (9, "System prompt tokens", 3000, "", "#,##0"),
    (10, "Task tokens", 1000, "The user's request plus any attached context", "#,##0"),
    (11, "Tools sent each call", 30, "Every definition is input tokens on every call", "0"),
    (12, "Tokens per tool definition", 500, "Name + description + JSON schema; real ones run ~100 to 1,000+", "#,##0"),
    (13, "Visible output per call", 300, "Tool call + short note; stays in the history", "#,##0"),
    (14, "Thinking tokens per call", 1500, "Billed as output; not carried in the history", "#,##0"),
    (15, "Input price ($ / million tokens)", 2, "Claude Sonnet 5.5 list price, Nov 2026: check your provider", "$0.00"),
    (16, "Output price ($ / million tokens)", 10, "Thinking is billed at this rate", "$0.00"),
    (17, "Cache read (× input price)", 0.1, "Anthropic: reads at 10% of input", "0.00x"),
    (18, "Cache write (× input price)", 1.25, "Anthropic: 5-minute writes at 125% (1-hour: 200%)", "0.00x"),
    (20, "Trimmed result tokens", 1000, "Fix 2: grep the lines that matter", "#,##0"),
    (21, "Tools after filtering", 6, "Fix 6: only what this step needs", "0"),
    (22, "Thinking tokens at low effort", 400, "Fix 7", "#,##0"),
    (23, "Re-checks skipped by stopping", 3, "Fix 5: calls made after the check already passed", "0"),
    (24, "Share of tool calls that are independent reads", 0.58, "Fix 4: these can run together", "0%"),
    (25, "Reads per parallel call", 3, "Fix 4", "0"),
    (26, "Prune when this many full results", 6, "Fix 3: prune in batches, so the cache survives between batches", "0"),
    (27, "Keep this many in full", 3, "Fix 3", "0"),
    (28, "Tokens per summary", 150, "Fix 3", "#,##0"),
]
c["A5"] = "Your agent"; c["A5"].font = H2; c["A19"] = "Fix settings"; c["A19"].font = H2
for r, lab, v, note, fmt in INPUTS:
    c.cell(r, 1, lab).font = BLACK; x = c.cell(r, 2, v); x.font = BLUE; x.number_format = fmt; x.fill = SOFT; c.cell(r, 3, note).font = GREY
SWITCH = [(31, "Cache the stable prefix", "1"), (32, "Trim tool results", "2"), (33, "Prune old results (in batches)", "3"),
          (34, "Run independent tools in parallel", "4"), (35, "Stop when the check passes", "5"), (36, "Filter the tools", "6"), (37, "Lower the effort", "7")]
c["A30"] = "The seven fixes (1 = on, 0 = off)"; c["A30"].font = H2
for i, (r, lab, n) in enumerate(SWITCH):
    c.cell(r, 1, f"{n}. {lab}").font = BLACK; x = c.cell(r, 2, int(SW[i])); x.font = BLUE; x.fill = YEL; x.alignment = Alignment(horizontal="center")
I = lambda r: f"Calculator!$B${r}"
CACHE, TRIM, PRUNE, PAR, STOP, FILT, LOW = (I(r) for r, _, _ in SWITCH)

# ---------------- Calls sheet: derived values, then one row per call ----------------
k["A1"] = "Call by call: each call re-sends the prefix plus everything earlier calls added"; k["A1"].font = H2
DER = [(3, "Tool calls (with the fixes)", f"=MAX(0,{I(7)}-{STOP}*{I(23)})"),
       (4, "Reads sent in parallel", f"=IF({PAR}=1,MIN(B3,ROUND({I(7)}*{I(24)},0)),0)"),
       (5, "Parallel calls", f"=IF(B4>0,ROUNDUP(B4/{I(25)},0),0)"),
       (6, "Model calls (with the fixes)", "=B5+(B3-B4)+1"),
       (7, "Prefix tokens (with the fixes)", f"={I(9)}+{I(10)}+{I(12)}*IF({FILT}=1,MIN({I(21)},{I(11)}),{I(11)})"),
       (8, "Output tokens per call (with the fixes)", f"={I(13)}+IF({LOW}=1,MIN({I(22)},{I(14)}),{I(14)})"),
       (9, "Tokens per result (with the fixes)", f"=IF({TRIM}=1,MIN({I(20)},{I(8)}),{I(8)})"),
       (10, "Model calls (now)", f"={I(7)}+1"),
       (11, "Prefix tokens (now)", f"={I(9)}+{I(10)}+{I(11)}*{I(12)}"),
       (12, "Output tokens per call (now)", f"={I(13)}+{I(14)}")]
for r, lab, f in DER:
    k.cell(r, 1, lab).font = BLACK; x = k.cell(r, 2, f); x.font = BLACK; x.number_format = "#,##0"
HDR = ["Call", "Now: active", "Now: input tokens", "Now: cost ($)", "Fixed: active", "Calls done", "Results so far", "Full results",
       "Summaries", "Fixed: input tokens", "Cache read tokens", "Input cost ($ × 1M)", "Fixed: cost ($)"]
for j, h in enumerate(HDR, 1):
    x = k.cell(14, j, h); x.font = BOLD; x.border = line; x.alignment = Alignment(wrap_text=True)
FIRST, LAST = 15, 74
GS, PA, KL, ST, CT = I(25), I(26), I(27), I(28), I(13)
for r in range(FIRST, LAST + 1):
    n = r - FIRST + 1; p = r - 1
    callof = f"IF((I{p}+1)<=$B$4,ROUNDUP((I{p}+1)/{GS},0),$B$5+((I{p}+1)-$B$4))"
    row = [n,
           f"=IF(A{r}<=$B$10,1,0)",
           f"=$B$11+(A{r}-1)*({CT}+{I(8)})",
           f"=B{r}*(C{r}*{I(15)}+$B$12*{I(16)})/1000000",
           f"=IF(A{r}<=$B$6,1,0)",
           f"=A{r}-1",
           f"=MIN({GS}*MIN(F{r},$B$5),$B$4)+MAX(0,F{r}-$B$5)",
           f"=IF({PRUNE}=1,IF(G{r}<{PA},G{r},{KL}+MOD(G{r}-{KL},MAX(1,{PA}-{KL}))),G{r})",
           f"=G{r}-H{r}",
           f"=$B$7+F{r}*{CT}+H{r}*$B$9+I{r}*{ST}",
           "=0" if r == FIRST else f"=IF(I{r}>I{p},$B$7+I{p}*{ST}+{callof}*{CT},J{p})",
           f"=IF({CACHE}=1,K{r}*{I(15)}*{I(17)}+(J{r}-K{r})*{I(15)}*{I(18)},J{r}*{I(15)})",
           f"=E{r}*(L{r}+$B$8*{I(16)})/1000000"]
    for j, v in enumerate(row, 1):
        x = k.cell(r, j, v); x.font = BLACK
        x.number_format = "$0.0000" if j in (4, 13) else ("#,##0" if j != 12 else "#,##0")
k.cell(LAST + 1, 1, "Total per run").font = BOLD
for col in ("D", "M"):
    x = k[f"{col}{LAST + 1}"]; x.value = f"=SUM({col}{FIRST}:{col}{LAST})"; x.font = BOLD; x.number_format = "$0.0000"
k.cell(LAST + 3, 1, "Caching: a call reads from cache the prefix it shares with the previous call. Pruning edits old results, so the cache is "
                    "re-written from the first changed result; batching keeps that rare. Same model as agent_cost/simulate.py.").font = GREY

# ---------------- results on the Calculator sheet ----------------
c["E5"] = "Results"; c["E5"].font = H2
RES = [(6, "Per run, now", f"=Calls!$D${LAST + 1}", "$0.00"), (7, "Per run, with the fixes on", f"=Calls!$M${LAST + 1}", "$0.00"),
       (8, "Model calls per run, now", "=Calls!$B$10", "0"), (9, "Model calls per run, with the fixes", "=Calls!$B$6", "0"),
       (10, "Per month, now (30 days)", "=F6*$B$6*30", "$#,##0"), (11, "Per month, with the fixes", "=F7*$B$6*30", "$#,##0"),
       (12, "Saved", "=IF(F6>0,1-F7/F6,0)", "0%")]
for r, lab, f, fmt in RES:
    c.cell(r, 5, lab).font = BLACK; x = c.cell(r, 6, f); x.number_format = fmt; x.font = Font(name=F, bold=r in (10, 11, 12), size=12 if r >= 10 else 10)
c["F11"].fill = HI
c["E14"] = "A model of one typical run, not your invoice: measure your own agent with the kit's benchmark."; c["E14"].font = GREY
c["B15"].comment = Comment("Check your provider's pricing page; these are list prices used in the kit's examples.", "tirthaexe")
c.column_dimensions["A"].width = 44; c.column_dimensions["B"].width = 12; c.column_dimensions["C"].width = 58
c.column_dimensions["D"].width = 3; c.column_dimensions["E"].width = 36; c.column_dimensions["F"].width = 14
k.column_dimensions["A"].width = 40
for col in "BCDEFGHIJKLM": k.column_dimensions[col].width = 14
k.row_dimensions[14].height = 32; c.freeze_panes = "A5"; k.freeze_panes = "B15"
wb.save(OUT); print(OUT)
