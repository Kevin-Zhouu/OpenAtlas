"""Launch upstream MCP with OpenAtlas's explicit telemetry opt-out."""

# The launcher shares /opt with blender_mcp.py; don't shadow the installed package.
import sys

sys.path.remove("/opt")

from blender_mcp import consent_prompt
from blender_mcp.server import main


async def no_telemetry_prompt(ctx):
    # Upstream's elicitation flow doesn't check its environment opt-out.
    # OpenAtlas disables collection for disposable jobs, so never ask to enable it.
    return ""


consent_prompt.maybe_prompt_for_consent = no_telemetry_prompt
main()
