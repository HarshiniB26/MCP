import asyncio

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    server = StdioServerParameters(command="python", args=["server.py"])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:", [tool.name for tool in tools.tools])
            result = await session.call_tool(
                "flag_for_human_review",
                arguments={
                    "employee_id": "E1004",
                    "request": "Please replace my laptop.",
                    "reason": "Issue date is missing, so the wait period cannot be checked.",
                },
            )
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
