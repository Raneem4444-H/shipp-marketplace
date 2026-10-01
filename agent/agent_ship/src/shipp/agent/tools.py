import importlib

importlib.invalidate_caches()

from shipp.agent.tools import ToolBox, ToolContext, TOOL_SPECS

print("PASS — shipp.agent.tools imports correctly")
print("ToolBox:", ToolBox)
print("ToolContext:", ToolContext)
print("Tool count:", len(TOOL_SPECS))