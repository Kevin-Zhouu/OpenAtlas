"""Runs only in the disposable container. No shell or orchestration tools."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from agents import (
    Agent,
    ItemHelpers,
    OpenAIResponsesModel,
    Runner,
    function_tool,
    set_tracing_disabled,
)
from openai import APIError, AsyncOpenAI

ROOT = Path("/workspace/skills")
REFERENCES = Path("/workspace/references")
READ = set()
REFERENCE_READS = []


def emit(kind, **fields):
    print(json.dumps({"type": kind, **fields}), flush=True)


def error_message(error):
    """Keep actionable provider errors without exposing credentials or requests."""
    detail = error.message if isinstance(error, APIError) else str(error)
    detail = detail or type(error).__name__
    for name in ("CODEX_API_KEY", "OPENAI_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            detail = detail.replace(secret, "[redacted]")
    detail = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[redacted]", detail)
    detail = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]+", r"\1[redacted]", detail)
    return "Planning failed: " + type(error).__name__ + ": " + detail[:1000]


@function_tool
async def list_resources() -> str:
    """List selected skill files and packaged golden reference records/images."""
    paths = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file())
    paths += sorted(
        "references/" + str(p.relative_to(REFERENCES))
        for p in REFERENCES.rglob("*")
        if p.is_file()
    )
    emit("planner.resources", paths=paths)
    return "\n".join(paths)


@function_tool
async def read_resource(path: str, offset: int = 0) -> str:
    """Read a UTF-8 skill or reference record in 24000-character chunks; not images."""
    is_reference = path.startswith("references/")
    root = REFERENCES if is_reference else ROOT
    relative = path[len("references/") :] if is_reference else path
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file() or offset < 0:
        raise ValueError("Resource outside selected skills or invalid offset")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(
            "Text-only resource reader cannot inspect images or binary files"
        ) from error
    if is_reference:
        REFERENCE_READS.append(
            {
                "path": path,
                "offset": offset,
                "characters": len(content[offset : offset + 24000]),
            }
        )
    elif offset == 0:
        READ.add(str(target.relative_to(ROOT)))
    emit(
        "planner.resource_read",
        path=path,
        offset=offset,
        characters=len(content[offset : offset + 24000]),
    )
    return content[offset : offset + 24000]


async def main():
    model, instructions, user_input = sys.argv[1:]
    set_tracing_disabled(True)
    subscription = os.environ.get("OPENATLAS_AUTH_MODE") == "chatgpt"
    if subscription:
        from subscription_model import SubscriptionModel
        inference_model = SubscriptionModel(model)
    else:
        client = AsyncOpenAI(
            api_key=os.environ["CODEX_API_KEY"], base_url="http://127.0.0.1:9000/v1"
        )
        inference_model = OpenAIResponsesModel(model=model, openai_client=client)
    agent = Agent(
        name="Notebook planner",
        instructions=instructions,
        model=inference_model,
        tools=[list_resources, read_resource],
    )
    emit("planner.started", model=model, authentication="chatgpt" if subscription else "api_key")
    if subscription:
        result = await Runner.run(agent, input=user_input, max_turns=40)
        emit("item.completed", item={"type": "agent_message", "text": result.final_output})
    else:
        result = Runner.run_streamed(agent, input=user_input, max_turns=40)
        async for event in result.stream_events():
            if event.type == "run_item_stream_event":
                item = event.item
                if item.type == "message_output_item":
                    emit(
                        "item.completed",
                        item={
                            "type": "agent_message",
                            "text": ItemHelpers.text_message_output(item),
                        },
                    )
                elif item.type in ("tool_call_item", "tool_call_output_item"):
                    emit("planner.activity", name=event.name)
    required = {str(p.relative_to(ROOT)) for p in ROOT.glob("*/SKILL.md")}
    if not required <= READ:
        raise ValueError("Planner did not read every selected SKILL.md")
    if (REFERENCES / "goldens/CATALOG.json").is_file() and not any(
        r["path"] == "references/goldens/CATALOG.json" and r["offset"] == 0
        for r in REFERENCE_READS
    ):
        raise ValueError("Planner did not read the golden reference catalog")
    if not isinstance(result.final_output, str):
        raise ValueError("Missing text output")
    output = result.final_output.strip()
    if (
        not 40 <= len(output) <= 40000
        or output.startswith(("{", "[", "```", "<!DOCTYPE", "<html"))
        or "\x00" in output
    ):
        raise ValueError("Expected a complete Markdown build brief")
    ledger = "\n\n## Resource access record (recorded by OpenAtlas)\n"
    if REFERENCE_READS:
        ledger += (
            "Text reads only; these do not verify image viewing or live interaction.\n"
        )
        ledger += "\n".join(
            f"- {r['path']} — offset {r['offset']}, {r['characters']} characters"
            for r in REFERENCE_READS
        )
    else:
        ledger += "No packaged golden reference records were read. Reference inspection is unverified."
    Path("/workspace/plan.md").write_text(output + ledger)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        emit("error", message=error_message(error))
        sys.exit(1)
