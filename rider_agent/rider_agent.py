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
    """Build StdioServerParameters pointing to rider_mcp.py."""
    here = Path(__file__).resolve().parent
    mcp_script = here / "rider_mcp.py"
    return StdioServerParameters(
        command="python",
        args=[str(mcp_script)],
    )


def create_rider_agent() -> LlmAgent:
    """Create the Rider LlmAgent that uses the maps MCP tools."""
    # model_name = os.getenv("LITELLM_MODEL", "gemini-2.5-flash")
    # model_name = os.getenv("LITELLM_MODEL", "gemini/gemini-2.0-flash")
    # api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    # model = LiteLlm(
    #     model=model_name,
    #     api_key=api_key,        # 👈 important: no ADC, just API key
    # )

    instruction = """
    You are the RiderAgent in a food delivery platform.

    You have tools from the "maps" MCP server, including:
    - get_directions(origin, destination)

    Behavior:
    1. Given restaurant and customer locations, call get_directions
       to compute distance and travel time.
    2. Return a JSON-style answer like:
       {
         "origin": "...",
         "destination": "...",
         "distance_km": 3.2,
         "eta_minutes": 14.5
       }
    3. Do not guess values – always use the tool.
    """

    return LlmAgent(
        model="gemini-2.5-flash",
        name="rider_agent",
        description="Uses maps MCP to compute routes and ETAs for riders.",
        instruction=instruction,
        tools=[
            MCPToolset(
                connection_params=_mcp_server_params(),
            )
        ],
    )


# if __name__ == "__main__":
#     # Simple local test
#     import asyncio
#     from google.adk.runners import Runner

#     async def _demo():
#         agent = create_rider_agent()
#         runner = Runner(agent)
#         user_query = (
#             "From 'MG Road, Bengaluru' to 'Indiranagar, Bengaluru', "
#             "what is the driving distance and ETA?"
#         )
#         result = await runner.run(user_query)
#         print("AGENT RESPONSE:\n", result.text)

#     asyncio.run(_demo())
