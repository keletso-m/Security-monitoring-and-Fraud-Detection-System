from mcp.server import MCPServer

mcp = MCPServer(
    "sentinel",
    instructions="Security analyst for Sentinel: reads incidents and explains risk scores.",
)


@mcp.tool()
def ping() -> str:
    """Check that the Sentinel MCP server is up."""
    return "pong"


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8765)
