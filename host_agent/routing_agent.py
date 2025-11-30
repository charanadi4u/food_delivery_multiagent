import asyncio
import os
from typing import Any

import httpx
from dotenv import load_dotenv

from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    MessageSendParams,
    Part,
    SendMessageRequest,
)
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from remote_agent_connection import RemoteAgentConnection

load_dotenv()


class RoutingAgent:
    """Routing layer that connects the host ADK agent to remote A2A agents."""

    def __init__(self, rider_conn: RemoteAgentConnection, restaurant_conn: RemoteAgentConnection):
        self.rider_conn = rider_conn
        self.restaurant_conn = restaurant_conn

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @classmethod
    async def create(cls, remote_agent_addresses: list[str]) -> "RoutingAgent":
        """Resolve remote agent cards and create RemoteAgentConnection objects.

        remote_agent_addresses: [rider_url, restaurant_url]
        """
        async with httpx.AsyncClient(timeout=30) as client:
            rider_url, restaurant_url = remote_agent_addresses

            # Resolve rider card
            rider_resolver = A2ACardResolver(client, rider_url)
            rider_card: AgentCard = await rider_resolver.get_agent_card()

            # Resolve restaurant card
            rest_resolver = A2ACardResolver(client, restaurant_url)
            restaurant_card: AgentCard = await rest_resolver.get_agent_card()

        rider_conn = RemoteAgentConnection(rider_url, rider_card)
        restaurant_conn = RemoteAgentConnection(restaurant_url, restaurant_card)

        return cls(rider_conn=rider_conn, restaurant_conn=restaurant_conn)

    # ------------------------------------------------------------------
    # Raw A2A helpers
    # ------------------------------------------------------------------
    async def call_rider(self, text: str) -> str:
        """Generic tool: send arbitrary text to rider A2A agent and return its text reply."""
        req = SendMessageRequest(
            params=MessageSendParams(
                message={
                    "role": "user",
                    "parts": [Part(kind="text", text=text)],
                }
            )
        )
        resp = await self.rider_conn.send_message(req)
        task = resp.result.task
        status_msg = task.status.message
        parts = status_msg.parts
        if parts and parts[0].kind == "text":
            return parts[0].text
        return "Rider agent returned no text."

    async def call_restaurant(self, text: str) -> str:
        """Generic tool: send arbitrary text to restaurant A2A agent and return its text reply."""
        req = SendMessageRequest(
            params=MessageSendParams(
                message={
                    "role": "user",
                    "parts": [Part(kind="text", text=text)],
                }
            )
        )
        resp = await self.restaurant_conn.send_message(req)
        task = resp.result.task
        status_msg = task.status.message
        parts = status_msg.parts
        if parts and parts[0].kind == "text":
            return parts[0].text
        return "Restaurant agent returned no text."

    # ------------------------------------------------------------------
    # High-level restaurant tool: prep time + total price
    # ------------------------------------------------------------------
    async def ask_restaurant_prep_and_price(
        self,
        restaurant_id: int,
        menu_item_ids: list[int],
    ) -> str:
        """Special tool: ask restaurant_agent to compute prep time and total price."""
        query = (
            "You are the RestaurantAgent. "
            f"Given restaurant_id={restaurant_id} and menu_item_ids={menu_item_ids}, "
            "please use your tools (get_restaurant, get_menu, estimate_prep_time) to:\n"
            "1. Validate the restaurant exists.\n"
            "2. Fetch the menu items and their prices.\n"
            "3. Compute the total price of the selected items.\n"
            "4. Estimate the preparation time in minutes.\n"
            "Return a JSON object with keys:\n"
            "  restaurant_id, restaurant_name, item_ids, total_price_inr, estimated_prep_minutes.\n"
            "Do not include any additional commentary outside the JSON."
        )

        req = SendMessageRequest(
            params=MessageSendParams(
                message={
                    "role": "user",
                    "parts": [Part(kind="text", text=query)],
                }
            )
        )
        resp = await self.restaurant_conn.send_message(req)
        task = resp.result.task
        status_msg = task.status.message
        parts = status_msg.parts
        if parts and parts[0].kind == "text":
            return parts[0].text
        return "Restaurant agent did not return JSON text."

    # ------------------------------------------------------------------
    # Build the host ADK LlmAgent
    # ------------------------------------------------------------------
    def create_agent(self) -> LlmAgent:
        """Build the host ADK LlmAgent that can call tools for rider & restaurant."""
        model_name = os.getenv("LITELLM_MODEL", "gemini-2.5-flash")

        async def rider_tool(query: str) -> str:
            return await self.call_rider(query)

        async def restaurant_tool(query: str) -> str:
            return await self.call_restaurant(query)

        async def restaurant_prep_tool(restaurant_id: int, menu_item_ids: list[int]) -> str:
            return await self.ask_restaurant_prep_and_price(restaurant_id, menu_item_ids)

        instruction = """
        You are the host FoodDeliveryOrchestrator.

        Tools you can call:

        1) rider_tool(query: str)
           - Sends a user query to the RiderAgent over A2A.
           - Use this when you want to assign riders or ask about rider ETA.

        2) restaurant_tool(query: str)
           - Sends a user query to the RestaurantAgent over A2A.
           - Use this for general menu questions, restaurant discovery, etc.

        3) restaurant_prep_tool(restaurant_id: int, menu_item_ids: list[int])
           - Asks the RestaurantAgent to compute total price and prep time
             for specific menu items at a given restaurant.
           - The RestaurantAgent will use its MCP tools (get_menu, estimate_prep_time)
             and return a JSON object with total_price_inr and estimated_prep_minutes.

        When planning a delivery:
        - First use restaurant_prep_tool to understand items, price, and prep time.
        - Then use rider_tool to coordinate rider assignment and overall ETA.
        - Finally, combine everything into a clear summary for the user.
        """

        return LlmAgent(
            model=LiteLlm(model=model_name),
            name="food_delivery_orchestrator",
            description="Host agent that coordinates restaurant & rider A2A agents and MCP-backed tools.",
            instruction=instruction,
            tools=[
                rider_tool,
                restaurant_tool,
                restaurant_prep_tool,
            ],
        )


def _get_initialized_routing_agent_sync() -> LlmAgent:
    async def _async_main() -> LlmAgent:
        routing = await RoutingAgent.create(
            remote_agent_addresses=[
                os.getenv("RIDER_AGENT_URL", "http://localhost:9001"),
                os.getenv("RESTAURANT_AGENT_URL", "http://localhost:9002"),
            ]
        )
        return routing.create_agent()

    try:
        return asyncio.run(_async_main())
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            print(
                "Warning: Could not initialize RoutingAgent with asyncio.run(). "
                "If you're in a Jupyter environment, initialize it in an async function."
            )
        raise


# Root agent used by host_agent.__main__
root_agent = _get_initialized_routing_agent_sync()
