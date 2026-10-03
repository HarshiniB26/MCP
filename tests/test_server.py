"""Protocol-level check: start server.py over stdio and talk to it as an MCP client.

The other test files call the plain functions directly. This one proves the
server registers all four tools and that a call travels through the protocol.
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER = str(Path(__file__).resolve().parents[1] / "server.py")
EXPECTED_TOOLS = {
    "get_employee_info",
    "get_policy_limits",
    "check_request_eligibility",
    "flag_for_human_review",
}


async def _with_session(action):
    params = StdioServerParameters(command=sys.executable, args=[SERVER])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await action(session)


def test_server_registers_all_four_tools():
    async def action(session):
        return {tool.name for tool in (await session.list_tools()).tools}

    assert asyncio.run(_with_session(action)) == EXPECTED_TOOLS


def test_tool_listing_shows_parameters_and_descriptions():
    from agent import tool_listing

    async def action(session):
        return tool_listing(await session.list_tools())

    listing = asyncio.run(_with_session(action))
    assert any(line.startswith("- get_employee_info(employee_id): ") for line in listing)
    assert any(line.startswith("- flag_for_human_review(employee_id, request, reason): ") for line in listing)


def test_judgement_question_shows_the_policy_and_the_employees_words():
    from agent import judgement_question, read_prompt
    from equipment.disposition import Investigation
    from equipment.eligibility import check_request_eligibility
    from equipment.employee_info import get_employee_info
    from equipment.policy_limits import get_policy_limits

    request = "Can I get a spare laptop? I'd like to keep the one I have."
    investigation = Investigation("E1001", request)
    investigation.observe("get_employee_info", get_employee_info("E1001", as_of="2026-10-02"))
    investigation.observe("get_policy_limits", get_policy_limits("standard"))
    arguments = {"employee_id": "E1001", "item": "laptop"}
    investigation.observe(
        "check_request_eligibility", check_request_eligibility("E1001", "laptop", as_of="2026-10-02"), arguments
    )

    question = judgement_question(read_prompt("judge"), investigation)
    assert "{allowed}" not in question and "{request}" not in question
    assert "laptop: allowed as a replacement only" in question
    assert f'"{request}"' in question


def test_tool_call_round_trips_through_protocol():
    async def action(session):
        result = await session.call_tool(
            "check_request_eligibility",
            arguments={"employee_id": "E1003", "item": "monitor"},
        )
        return json.loads(result.content[0].text)

    outcome = asyncio.run(_with_session(action))
    assert outcome["outcome"] == "eligible"
    assert outcome["count"] == 0
