from mcp.server.fastmcp import FastMCP
import tools

# Initialize FastMCP Server
mcp = FastMCP("GoogleDriveServer")

# Register the tools from tools.py
mcp.tool()(tools.get_file)
mcp.tool()(tools.get_many_files)
mcp.tool()(tools.get_file_content)
mcp.tool()(tools.delete_files)
mcp.tool()(tools.create_files)

if __name__ == "__main__":
    mcp.run(transport="stdio")