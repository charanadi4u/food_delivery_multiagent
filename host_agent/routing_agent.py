# host_agent/routing_agent.py

import asyncio
import os
import uuid
from typing import Any
import json

import httpx
from dotenv import load_dotenv

from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    Task,
)
from google.adk.agents import LlmAgent
from google.genai import types as genai_types

from remote_agent_connection import RemoteAgentConnection

load_dotenv()


class RoutingAgent:
    """
    Host/orchestrator that talks to remote A2A agents:

    - rider_conn: rider_agent A2A endpoint (maps/ETA via MCP)
    - restaurant_conn: restaurant_agent A2A endpoint (menu/prep via MCP)
    """

    def __init__(
        self,
        rider_conn: RemoteAgentConnection,
        restaurant_conn: RemoteAgentConnection,
    ) -> None:
        self.rider_conn = rider_conn
        self.restaurant_conn = restaurant_conn

    # ------------------------------------------------------------------
    # Factory: resolve remote A2A agent cards and build connections
    # ------------------------------------------------------------------
    @classmethod
    async def create(cls, remote_agent_addresses: list[str]) -> "RoutingAgent":
        """
        remote_agent_addresses: [rider_agent_url, restaurant_agent_url]
        """
        if len(remote_agent_addresses) != 2:
            raise ValueError(
                f"Expected 2 remote agent URLs (rider, restaurant), got {remote_agent_addresses}"
            )

        rider_url, restaurant_url = remote_agent_addresses

        async with httpx.AsyncClient(timeout=30) as client:
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
    # Low-level A2A helper
    # ------------------------------------------------------------------
    async def _send_text_to_agent(
        self,
        conn: RemoteAgentConnection,
        text: str,
    ) -> str:
        """
        Send a simple user text message to a remote A2A agent and
        return the final text content from the task status message.

        If there are no text parts, fall back to returning a JSON dump
        of the Task for debugging instead of raising.
        """
        message_id = str(uuid.uuid4())

        payload = {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "type": "text",  # NOTE: A2A uses 'type', not 'kind'
                        "text": text,
                    }
                ],
                "messageId": message_id,
            }
        }

        params = MessageSendParams.model_validate(payload)

        request = SendMessageRequest(
            id=message_id,
            params=params,
        )

        response = await conn.send_message(message_request=request)

        # Support both ResponseRoot[SendMessageResponse] and SendMessageResponse shapes
        root_like: Any = getattr(response, "root", response)
        task_obj: Task = root_like.result  # type: ignore[assignment]

        if not isinstance(task_obj, Task):
            # This really shouldn't happen, but let's debug gracefully.
            return f"REMOTE_AGENT_NON_TASK_RESULT: {task_obj!r}"

        status = task_obj.status

        # --- 1) Normal happy path: text parts in status.message.parts ---
        if (
            status
            and getattr(status, "message", None)
            and getattr(status.message, "parts", None)
        ):
            texts = []
            for part in status.message.parts:
                # Many part types exist (text, function_call, tool_output, etc.)
                if getattr(part, "text", None):
                    texts.append(part.text)
            if texts:
                return "\n".join(texts)

        # --- 2) Fallback: maybe the model put something useful in status.output / output_text ---
        if status:
            # Some ADK / A2A versions may expose consolidated output here
            output = getattr(status, "output", None)
            if output:
                try:
                    return json.dumps(output, indent=2, default=str)
                except Exception:
                    return str(output)

        # --- 3) Final fallback: dump the whole Task as JSON so we can see what's going on ---
        try:
            return json.dumps(task_obj.model_dump(), indent=2, default=str)
        except Exception:
            # Last resort: repr
            return f"REMOTE_AGENT_TASK_NO_TEXT_PARTS: {task_obj!r}"


    # ------------------------------------------------------------------
    # Public helpers used by tools
    # ------------------------------------------------------------------
    async def call_rider(self, text: str) -> str:
        """Send arbitrary text to the rider A2A agent and return its reply text."""
        return await self._send_text_to_agent(self.rider_conn, text)

    async def call_restaurant(self, text: str) -> str:
        """Send arbitrary text to the restaurant A2A agent and return its reply text."""
        return await self._send_text_to_agent(self.restaurant_conn, text)

    async def ask_restaurant_prep_and_price(
        self,
        restaurant_id: int,
        menu_item_ids: list[int],
    ) -> str:
        """
        Special helper: ask RestaurantAgent to compute prep time + total price.

        Returns JSON text from the restaurant agent, e.g.:

        {
          "restaurant_id": 1,
          "restaurant_name": "Spice Hub",
          "item_ids": [1, 2],
          "total_price_inr": 340.0,
          "estimated_prep_minutes": 22
        }
        """
        query = (
            "You are the RestaurantAgent. "
            f"Given restaurant_id={restaurant_id} and menu_item_ids={menu_item_ids}, "
            "please use your tools (get_restaurant, get_menu, estimate_prep_time) to:\n"
            "1. Validate the restaurant exists.\n"
            "2. Fetch the menu items and their prices.\n"
            "3. Compute the total price of the selected items.\n"
            "4. Estimate the preparation time in minutes.\n"
            "Return ONLY a JSON object with keys:\n"
            "  restaurant_id, restaurant_name, item_ids, total_price_inr, estimated_prep_minutes.\n"
            "Do not include any additional commentary outside the JSON."
        )

        return await self._send_text_to_agent(self.restaurant_conn, query)

    # ------------------------------------------------------------------
    # Build the host ADK LlmAgent (orchestrator)
    # ------------------------------------------------------------------
    def create_agent(self) -> LlmAgent:
        """
        Build the host LlmAgent that exposes tools for:
        - rider_tool
        - restaurant_tool
        - restaurant_prep_tool
        """
        async def rider_tool(query: str) -> str:
            return await self.call_rider(query)

        async def restaurant_tool(query: str) -> str:
            return await self.call_restaurant(query)

        async def restaurant_prep_tool(
            restaurant_id: int, menu_item_ids: list[int]
        ) -> str:
            return await self.ask_restaurant_prep_and_price(
                restaurant_id, menu_item_ids
            )

        instruction = """
You are the FoodDeliveryOrchestrator host agent.

The END USER will speak in NATURAL LANGUAGE and does NOT know internal database IDs.

You have three tools:

1) rider_tool(query: str)
   - Sends a user query to the RiderAgent over A2A.
   - Use this when you want to compute distance/ETA between restaurant and customer.

2) restaurant_tool(query: str)
   - Sends a user query to the RestaurantAgent over A2A.
   - Use this for general menu questions, restaurant discovery, etc.

3) restaurant_prep_tool(restaurant_id: int, menu_item_ids: list[int])
   - Asks the RestaurantAgent to compute total price and prep time for specific items.
   - The RestaurantAgent will use its MCP tools (get_menu, estimate_prep_time)
     and return a JSON object with:
       restaurant_id, restaurant_name, item_ids, total_price_inr, estimated_prep_minutes.

VERY IMPORTANT:
- The USER will say restaurant names and dish names, like:
    - "Spice Hub"
    - "Paneer Tikka", "Butter Naan"
- The USER will NOT say "restaurant_id=1" or "item_ids=[1,2]".
- YOU (the host agent) must translate NAMES → INTERNAL IDs using the mapping below,
  then call restaurant_prep_tool with the correct IDs.

Current restaurant/menu mapping (keep this in your memory and use it):

- Restaurant 1: "Spice Hub"
    - Menu item 1: "Paneer Tikka"
    - Menu item 2: "Butter Naan"
    - Menu item 3: "Veg Biryani"

(If the user says "Spice Hub", treat that as restaurant_id=1.
 If the user says "Paneer Tikka", include item_id=1.
 If "Butter Naan", include item_id=2, etc.)

When planning a delivery:
- First:
    - Parse the user's sentence to identify restaurant name and dish names.
    - Map them to restaurant_id and menu_item_ids using the mapping above.
    - Call restaurant_prep_tool(restaurant_id, menu_item_ids) to get price + prep time.
- Then:
    - Use rider_tool(query) to compute distance and rider ETA between pickup and delivery addresses.
- Finally:
    - Combine everything in a clear final answer to the user, for example:

      "Total price: 340 INR
       Kitchen prep time: 25 minutes
       Rider ETA: 12.2 minutes
       Approximate delivery completion time: ~37 minutes."

Whenever the user speaks in names, NEVER ask them for numeric IDs.
Internally, you figure out the IDs from this mapping and call the tools.
""".strip()

        return LlmAgent(
            model="gemini-2.5-flash",
            name="food_delivery_orchestrator",
            description=(
                "Host agent that coordinates restaurant & rider A2A agents "
                "and MCP-backed tools."
            ),
            instruction=instruction,
            tools=[rider_tool, restaurant_tool, restaurant_prep_tool],
            generate_content_config=genai_types.GenerateContentConfig(
                max_output_tokens=1024,
            ),
        )


# ----------------------------------------------------------------------
# Helper to build the root agent synchronously (used by __main__.py)
# ----------------------------------------------------------------------
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


# This is what host_agent/__main__.py imports
root_agent = _get_initialized_routing_agent_sync()
