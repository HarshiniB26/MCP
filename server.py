from mcp.server import MCPServer

from employee_info import get_employee_info as lookup_employee
from eligibility import check_request_eligibility as lookup_eligibility
from policy_limits import get_policy_limits as lookup_policy

mcp = MCPServer("Equipment Request Server")


@mcp.tool()
def get_employee_info(employee_id: str) -> dict:
    """Return role, tenure, and current equipment for an employee id."""
    return lookup_employee(employee_id)


@mcp.tool()
def get_policy_limits(role: str) -> dict:
    """Return what a role may have and how often."""
    return lookup_policy(role)


@mcp.tool()
def check_request_eligibility(employee_id: str, item: str) -> dict:
    """Return whether an item is inside the role limit. Does not read the reason."""
    return lookup_eligibility(employee_id, item)


if __name__ == "__main__":
    mcp.run()
