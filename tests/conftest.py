import asyncio

import pytest

import agent
from equipment.traceability import MemoryRecord


@pytest.fixture
def run_agent():
    """Run the real agent pipeline (MCP server, ReAct loop, judgement, reflection) for one request."""

    def run(model, employee_id, request_text):
        record = MemoryRecord()
        asyncio.run(agent._decide(model, employee_id, request_text, record))
        return record

    return run
