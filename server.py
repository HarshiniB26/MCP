from mcp.server import MCPServer

from employee_info import get_employee_info as lookup_employee

mcp = MCPServer("Equipment Request Server")


@mcp.tool()
def get_employee_info(employee_id: str) -> dict:
    """Return role, tenure, and current equipment for an employee id."""
    return lookup_employee(employee_id)


if __name__ == "__main__":
    mcp.run()
