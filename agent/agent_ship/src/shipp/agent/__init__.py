"""SHIPP AI agent package.

Runtime code imports concrete modules directly to avoid eager package
initialization and circular/re-entrant imports during application startup.
"""