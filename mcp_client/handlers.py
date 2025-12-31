import os

from dotenv import load_dotenv
from mcp import ClientSession
from anthropic import Anthropic

# Load environment variables from .env file
load_dotenv()


MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1000


class ClaudeQueryHandler:
    """Handle Anthropic Claude API interaction and MCP tool execution"""

    def __init__(self, client_session: ClientSession):
        self.client_session = client_session
        if not (api_key := os.getenv("ANTHROPIC_API_KEY")):
            raise RuntimeError(
                "Error: ANTHROPIC_API_KEY environment variable not set",
            )
        self.anthropic = Anthropic(api_key=api_key)

    async def process_query(self, query: str) -> str:
        """Process a query using Anthropic Claude and available MCP tools."""
        # Get initial model's response and decision on tool calls
        messages = [{"role": "user", "content": query}]
        tools = await self._get_tools()

        initial_response = self.anthropic.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=messages,
            tools=tools,
        )

        result_parts = []

        # Handle text content
        for content in initial_response.content:
            if content.type == "text":
                result_parts.append(content.text)

        # Handle tool usage if present
        tool_use_blocks = [
            block for block in initial_response.content if block.type == "tool_use"
        ]

        if tool_use_blocks:
            messages.append({"role": "assistant", "content": initial_response.content})

            # Execute tools
            tool_results = []
            for tool_block in tool_use_blocks:
                tool_result = await self._execute_tool(tool_block)
                result_parts.append(tool_result["log"])
                tool_results.append(tool_result["message"])

            messages.extend(tool_results)

            # Get final model's response after tool execution
            final_response = self.anthropic.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=messages,
            )

            for content in final_response.content:
                if content.type == "text":
                    result_parts.append(content.text)

        return "Assistant: " + "\n".join(result_parts)

    async def _get_tools(self) -> list:
        """Get MCP tools formatted for Claude."""
        response = await self.client_session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "No description",
                "input_schema": getattr(
                    tool,
                    "inputSchema",
                    {"type": "object", "properties": {}},
                ),
            }
            for tool in response.tools
        ]

    async def _execute_tool(self, tool_block) -> dict:
        """Execute an MCP tool call and return formatted result."""
        tool_name = tool_block.name
        tool_args = tool_block.input

        try:
            result = await self.client_session.call_tool(
                tool_name,
                tool_args,
            )
            content = result.content[0].text if result.content else ""
            log = f"[Used {tool_name}({tool_args})]"
        except Exception as e:
            content = f"Error: {e}"
            log = f"[{content}]"

        return {
            "log": log,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": content,
                    }
                ],
            },
        }
