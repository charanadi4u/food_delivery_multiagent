import os
from pathlib import Path

from dotenv import load_dotenv

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioServerParameters,
)

load_dotenv()


def _mcp_server_params() -> StdioServerParameters:
    """Build StdioServerParameters pointing to restaurant_mcp.py."""
    here = Path(__file__).resolve().parent
    mcp_script = here / "restaurant_mcp.py"

    return StdioServerParameters(
        command="python",
        args=[str(mcp_script)],
    )


def create_restaurant_agent() -> LlmAgent:
    """Create the Restaurant LlmAgent that uses the restaurant_db MCP tools."""
    model_name = os.getenv("LITELLM_MODEL", "gemini-2.5-flash")

    instruction = """
    You are the RestaurantAgent in a food delivery platform.

    You have tools from the "restaurant_db" MCP server, including:
    - list_restaurants(cuisine_filter, only_open, limit)
    - get_restaurant(restaurant_id)
    - get_menu(restaurant_id, only_available)
    - estimate_prep_time(restaurant_id, menu_item_ids)
    - search_menu_items(text, limit)

    General behavior:
    1. When the host or user asks about a specific restaurant and items:
       - First call `get_restaurant(restaurant_id)` to validate the restaurant exists.
       - Then call `get_menu(restaurant_id)` to see available items and their prices.
       - Use `estimate_prep_time(restaurant_id, menu_item_ids)` to compute prep time.
       - Sum up item prices for the requested menu_item_ids to get total price.

    2. Return a concise JSON-style answer in your final message body, for example:
       {
         "restaurant_id": 1,
         "restaurant_name": "Spice Hub",
         "item_ids": [2, 3],
         "total_price_inr": 690.0,
         "estimated_prep_minutes": 22
       }

    3. Do NOT invent items or prices. Always rely on the tools.
    4. If a restaurant or item is missing, explain clearly what is missing.

    You can also handle discovery:
    - If the user only gives cuisine or text, use list_restaurants/search_menu_items
      first, then propose options.
    """

    return LlmAgent(
        model=LiteLlm(model=model_name),
        name="restaurant_agent",
        description=(
            "Uses restaurant_db MCP tools to fetch menus, prices, and estimate "
            "preparation times for selected items."
        ),
        instruction=instruction,
        tools=[
            MCPToolset(
                connection_params=_mcp_server_params(),
            )
        ],
    )


if __name__ == "__main__":
    # Simple local test
    import asyncio
    from google.adk.runners import Runner

    async def _demo():
        agent = create_restaurant_agent()
        runner = Runner(agent)
        user_query = (
            "For restaurant_id=1, if I order items [1,2], "
            "what is the total price and preparation time?"
        )
        result = await runner.run(user_query)
        print("AGENT RESPONSE:\n", result.text)

    asyncio.run(_demo())
