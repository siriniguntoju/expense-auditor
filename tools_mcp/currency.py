from mcp.server.fastmcp import FastMCP

from auditor.checks import convert_currency

server = FastMCP("synthetic-currency")
server.tool()(convert_currency)
if __name__ == "__main__":
    server.run(transport="stdio")
