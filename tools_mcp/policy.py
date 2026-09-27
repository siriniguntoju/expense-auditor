from mcp.server.fastmcp import FastMCP

from auditor.checks import check_policy

server = FastMCP("expense-policy")
server.tool()(check_policy)
if __name__ == "__main__":
    server.run(transport="stdio")
