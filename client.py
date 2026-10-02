import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

EXPECTED = {
    "get_employee_info",
    "get_policy_limits",
    "check_request_eligibility",
    "flag_for_human_review",
}


async def main():
    server_path = str(Path(__file__).resolve().parent / "server.py")
    server = StdioServerParameters(command=sys.executable, args=[server_path])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            print("Tools from the MCP server:")
            for tool in tools.tools:
                schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
                params = ", ".join(schema.get("properties", {})) if isinstance(schema, dict) else ""
                print(f"- {tool.name}({params}): {tool.description or ''}")
            print()
            missing = EXPECTED - names
            if missing:
                raise RuntimeError(f"Missing tools: {sorted(missing)}")
            employee = await session.call_tool(
                "get_employee_info",
                arguments={"employee_id": "E1003"},
            )
            eligibility = await session.call_tool(
                "check_request_eligibility",
                arguments={"employee_id": "E1003", "item": "monitor"},
            )
            review = await session.call_tool(
                "flag_for_human_review",
                arguments={
                    "employee_id": "E1004",
                    "request": "Please replace my laptop.",
                    "reason": "Issue date is missing, so the wait period cannot be checked.",
                },
            )
            for result in (employee, eligibility, review):
                if getattr(result, "isError", False) or getattr(result, "is_error", False):
                    raise RuntimeError(result)
                print(result.content[0].text)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
