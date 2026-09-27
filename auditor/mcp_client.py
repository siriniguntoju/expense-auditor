import json
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from auditor.paths import ROOT


@asynccontextmanager
async def tool_session(module):
    async with stdio_client(
        StdioServerParameters(command=sys.executable, args=["-m", module], cwd=str(ROOT))
    ) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            yield session


async def call(session, name, arguments):
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise ValueError(f"MCP tool {name} failed")
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)
