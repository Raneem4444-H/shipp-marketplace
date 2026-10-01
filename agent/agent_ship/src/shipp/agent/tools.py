import os
import sys
from pathlib import Path

current = Path(os.getcwd()).resolve()

repo_root = None

for parent in [current, *current.parents]:
    if (parent / "agent" / "agent_ship" / "src").exists():
        repo_root = parent
        break

if repo_root is None:
    raise RuntimeError(
        "Could not locate SHIPP repo root containing agent/agent_ship/src"
    )

agent_src = str(repo_root / "agent" / "agent_ship" / "src")

if agent_src not in sys.path:
    sys.path.insert(0, agent_src)

print("Repo root:", repo_root)
print("Agent src:", agent_src)

# import importlib

# importlib.invalidate_caches()

# from shipp.agent.tools import ToolBox, ToolContext, TOOL_SPECS

# print("PASS — shipp.agent.tools imports correctly")
# print("ToolBox:", ToolBox)
# print("ToolContext:", ToolContext)
# print("Tool count:", len(TOOL_SPECS))