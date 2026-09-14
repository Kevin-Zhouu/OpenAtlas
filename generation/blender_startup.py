"""Load the pinned addon into the container-local Blender event loop."""

import importlib.util
import sys

import bpy

spec = importlib.util.spec_from_file_location(
    "openatlas_blender_addon", "/opt/blender-mcp-source/addon.py"
)
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
bpy.types.blendermcp_server = addon.BlenderMCPServer(host="127.0.0.1", port=9876)
addon.register()
