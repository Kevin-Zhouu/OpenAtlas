"""Exercise the installed MCP protocol and image delivery without model inference."""

import asyncio
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    page = Path("/workspace/dist/index.html")
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "<!doctype html><title>Browser tool test</title><button onclick=\"this.textContent='Clicked'\">Try</button>"
    )
    server = StdioServerParameters(
        command="node",
        args=["/opt/browser-mcp/launch.cjs", "--allow-unrestricted-file-access"],
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            names = {tool.name for tool in listing.tools}
            assert {
                "browser_navigate",
                "browser_click",
                "browser_take_screenshot",
                "browser_evaluate",
            } <= names
            opened = await session.call_tool("browser_navigate", {"url": page.as_uri()})
            assert not opened.isError, opened
            capture = await session.call_tool(
                "browser_take_screenshot", {"type": "png", "filename": "smoke.png"}
            )
            assert not capture.isError, capture
            assert any(block.type == "image" for block in capture.content), (
                "Screenshot did not return image input to the model"
            )
            page.write_text("""<!doctype html><title>Large screenshot regression</title>
<canvas width="1600" height="1100"></canvas><script>
const c=document.querySelector('canvas'),x=c.getContext('2d'),d=x.createImageData(c.width,c.height);
let seed=123;for(let i=0;i<d.data.length;i+=4){for(let j=0;j<3;j++){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;d.data[i+j]=seed&255;}d.data[i+3]=255;}x.putImageData(d,0,0);
</script>""")
            resized = await session.call_tool(
                "browser_resize", {"width": 1600, "height": 1100}
            )
            assert not resized.isError, resized
            opened = await session.call_tool("browser_navigate", {"url": page.as_uri()})
            assert not opened.isError, opened
            large = await session.call_tool("browser_take_screenshot", {"type": "png"})
            assert not large.isError, large
            images = [block for block in large.content if block.type == "image"]
            assert images and images[0].mimeType == "image/jpeg"
            assert len(large.model_dump_json()) < 800000
            originals = list(Path("/workspace/source/review").glob("*.png"))
            assert max(p.stat().st_size for p in originals) > 1048576
            print(
                "PASS browser MCP navigation, direct images, and oversized screenshot transport with original files preserved"
            )


asyncio.run(main())
