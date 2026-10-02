import logging

from mcp.server import MCPServer

from equipment.employee_info import get_employee_info as lookup_employee
from equipment.eligibility import check_request_eligibility as lookup_eligibility
from equipment.errors import EquipmentError
from equipment.policy_limits import get_policy_limits as lookup_policy
from equipment.review import flag_for_human_review as save_review

logger = logging.getLogger("equipment.server")
mcp = MCPServer("Equipment Request Server")


def _tool_result(func, /, **kwargs):
    """Run a tool. Business results pass through. Failures become an error object."""
    try:
        return func(**kwargs)
    except EquipmentError as error:
        logger.error("%s failed: %s", func.__name__, error)
        return {"error": type(error).__name__, "message": str(error)}
    except Exception as error:
        logger.exception("%s failed", func.__name__)
        return {"error": type(error).__name__, "message": str(error)}


@mcp.tool()
def get_employee_info(employee_id: str) -> dict:
    """Return role, tenure, and current equipment for an employee id."""
    return _tool_result(lookup_employee, employee_id=employee_id)


@mcp.tool()
def get_policy_limits(role: str) -> dict:
    """Return what a role may have and how often."""
    return _tool_result(lookup_policy, role=role)


@mcp.tool()
def check_request_eligibility(employee_id: str, item: str) -> dict:
    """Return whether an item is inside the role limit. Does not read the reason."""
    return _tool_result(lookup_eligibility, employee_id=employee_id, item=item)


@mcp.tool()
def flag_for_human_review(employee_id: str, request: str, reason: str) -> dict:
    """Store an escalation for a human reviewer. Does not approve or deny."""
    return _tool_result(
        save_review,
        employee_id=employee_id,
        request=request,
        reason=reason,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    mcp.run()
