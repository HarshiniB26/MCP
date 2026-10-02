from mcp.server import MCPServer

mcp = MCPServer("Demo Server")

@mcp.tool()
def hello() -> str:
    return "Hello from my MCP server!"

if __name__ == "__main__":
    mcp.run()