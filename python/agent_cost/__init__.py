"""AI Agent Cost Kit (@tirthaexe): seven ways to cut an agent's API bill without changing models."""
from .cache import cached_system, cache_tools, cache_latest_turn, cache_report            # 1 cache the stable prefix
from .trim import trim_output, cap_tokens, estimate_tokens                               # 2 send the lines that matter
from .context import prune_tool_results, strip_private_keys, first_lines_summary          # 3 summarise old results, in batches
from .parallel import run_tool_uses                                                       # 4 run independent tools at once
from .stop import StopPolicy, stop_hint                                                   # 5 stop when the check passes
from .tools import select_tools, tool_tokens                                              # 6 only the tools this step needs
from .effort import pick_effort, anthropic_thinking, openai_reasoning                     # 7 effort to match the task
from .pricing import Price, SONNET, call_cost

__all__ = [n for n in dir() if not n.startswith("_")]
