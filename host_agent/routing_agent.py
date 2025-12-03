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
        *,
        label: str = "remote",
    ) -> str:
        """
        Send a simple user text message to a remote A2A agent and
        return the final text content from the task status message.

        If there are no text parts, fall back to returning a JSON dump
        of the Task for debugging instead of raising.

        This function logs the full lifecycle so you can see exactly
        what is being sent and what is coming back.
        """
        message_id = str(uuid.uuid4())

        print("\n[RoutingAgent] =======================================")
        print(f"[RoutingAgent] A2A SEND -> {label}")
        print(f"[RoutingAgent] message_id = {message_id}")
        print(f"[RoutingAgent] text = {text!r}")
        print("[RoutingAgent] =======================================\n")

        payload = {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "type": "text",  # A2A uses 'type'
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
            msg = f"REMOTE_AGENT_NON_TASK_RESULT: {task_obj!r}"
            print(f"[RoutingAgent] !!! {label} returned non-Task result: {msg}")
            return msg

        status = task_obj.status

        # --- 1) Normal happy path: text parts in status.message.parts ---
        if (
            status
            and getattr(status, "message", None)
            and getattr(status.message, "parts", None)
        ):
            texts = []
            for part in status.message.parts:
                if getattr(part, "text", None):
                    texts.append(part.text)

            if texts:
                joined = "\n".join(texts)
                print(f"[RoutingAgent] A2A RECV <- {label} (text parts):")
                print(joined)
                return joined

        # --- 2) Fallback: use status.output if present ---
        if status:
            output = getattr(status, "output", None)
            if output is not None:
                try:
                    dumped = json.dumps(output, indent=2, default=str)
                except Exception:
                    dumped = str(output)
                print(f"[RoutingAgent] A2A RECV <- {label} (status.output):")
                print(dumped)
                return dumped

        # --- 3) Final fallback: dump the whole Task as JSON ---
        try:
            dumped_task = json.dumps(task_obj.model_dump(), indent=2, default=str)
        except Exception:
            dumped_task = f"REMOTE_AGENT_TASK_NO_TEXT_PARTS: {task_obj!r}"

        print(f"[RoutingAgent] A2A RECV <- {label} (fallback Task dump):")
        print(dumped_task)
        return dumped_task

    # ------------------------------------------------------------------
    # Public helpers used by tools
    # ------------------------------------------------------------------
    async def call_rider(self, text: str) -> str:
        """Send arbitrary text to the rider A2A agent and return its reply text."""
        return await self._send_text_to_agent(self.rider_conn, text, label="rider")

    async def call_restaurant(self, text: str) -> str:
        """Send arbitrary text to the restaurant A2A agent and return its reply text."""
        return await self._send_text_to_agent(
            self.restaurant_conn,
            text,
            label="restaurant",
        )

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
            "4. Estimate the preparation time in minutes.\n\n"
            "Return ONLY a JSON object with keys:\n"
            "  restaurant_id, restaurant_name, item_ids, total_price_inr, estimated_prep_minutes.\n"
            "Do not include any additional commentary outside the JSON.\n"
            'If there is any problem (e.g. restaurant not found, DB error), '
            'return a JSON object with a top-level key "error" and a helpful '
            "error message string."
        )

        print(
            "[RoutingAgent] >>> ask_restaurant_prep_and_price("
            f"restaurant_id={restaurant_id}, menu_item_ids={menu_item_ids})"
        )

        result_text = await self._send_text_to_agent(
            self.restaurant_conn,
            query,
            label="restaurant-prep",
        )

        print("[RoutingAgent] <<< ask_restaurant_prep_and_price result:")
        print(result_text)
        return result_text

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
            print(f"[RoutingAgent] TOOL CALL rider_tool(query={query!r})")
            return await self.call_rider(query)

        async def restaurant_tool(query: str) -> str:
            print(f"[RoutingAgent] TOOL CALL restaurant_tool(query={query!r})")
            return await self.call_restaurant(query)

        async def restaurant_prep_tool(
            restaurant_id: int,
            menu_item_ids: list[int],
        ) -> str:
            """
            Tool the LLM must use to compute price + prep time.

            IMPORTANT: This function NEVER fabricates 'tools unresponsive'.
            It simply returns whatever JSON string the RestaurantAgent
            replied with. If there is a problem, the RestaurantAgent
            should include an "error" field in the JSON.
            """
            print(
                "[RoutingAgent] TOOL CALL restaurant_prep_tool("
                f"restaurant_id={restaurant_id}, menu_item_ids={menu_item_ids})"
            )
            try:
                result = await self.ask_restaurant_prep_and_price(
                    restaurant_id,
                    menu_item_ids,
                )
                return result
            except Exception as e:
                # We DO NOT put the phrase "tools unresponsive" here.
                # Instead we return a JSON object with an "error" field.
                print("[RoutingAgent] ERROR in restaurant_prep_tool:", repr(e))
                error_payload = {
                    "error": f"restaurant_prep_tool exception: {str(e)}",
                    "restaurant_id": restaurant_id,
                    "menu_item_ids": menu_item_ids,
                }
                return json.dumps(error_payload)

        instruction = """
You are the FoodDeliveryOrchestrator host agent.

The END USER speaks in NATURAL LANGUAGE and does NOT know internal database IDs.

You have three tools:

1) rider_tool(query: str)
   - Sends a query to the RiderAgent over A2A.
   - Use this to compute distance and rider ETA between restaurant and customer.

2) restaurant_tool(query: str)
   - Sends a query to the RestaurantAgent over A2A.
   - Use this for general menu questions, restaurant discovery, etc.

3) restaurant_prep_tool(restaurant_id: int, menu_item_ids: list[int])
   - Asks the RestaurantAgent to compute total price and prep time for specific items.
   - The RestaurantAgent will use its MCP tools (get_restaurant, get_menu, estimate_prep_time)
     and return a JSON object with:
       restaurant_id, restaurant_name, item_ids, total_price_inr, estimated_prep_minutes.
   - If there is a problem, the JSON will contain a top-level "error" field.

VERY IMPORTANT BEHAVIOR RULES:

- Whenever the user asks about:
    * ordering food,
    * price / bill,
    * kitchen preparation time,
    * delivery ETA,
  you MUST call the tools. Do NOT guess prices or prep times.

- Use restaurant_prep_tool to get price + prep time.
- Use rider_tool to get rider ETA.

- The USER speaks in names, e.g.:
    * "Spice Hub"
    * "Paneer Tikka", "Butter Naan"

- The USER does not say numeric IDs. Internally, YOU map names → IDs.

Current restaurant/menu mapping you MUST use:

- Restaurant 1: "Spice Hub"
    - Menu item 1: "Paneer Tikka"
    - Menu item 2: "Butter Naan"
    - Menu item 3: "Veg Biryani"

Mapping rules:

- If the user says "Spice Hub", treat that as restaurant_id = 1.
- If the user says "Paneer Tikka", include item_id = 1.
- If the user says "Butter Naan", include item_id = 2.
- If the user says "Veg Biryani", include item_id = 3.

Do NOT ask the user for numeric IDs; infer them from the names using this mapping.

FLOW WHEN USER REQUESTS AN ORDER:

1. Parse the user's request:
   - Identify the restaurant name and dish names from the text.
   - Map them to restaurant_id and menu_item_ids using the mapping above.

2. Call restaurant_prep_tool(restaurant_id, menu_item_ids):
   - Parse its JSON result.
   - If the result contains an "error" key, then and ONLY then
     explain to the user that there was an error with the restaurant
     system, and summarize the error in simple language.
   - If there is no "error" key, NEVER claim that the tools are broken
     or unresponsive.

3. For delivery time:
   - Identify pickup address (restaurant address) and drop address (user location).
   - Call rider_tool with a query that clearly states:
       - origin address
       - destination address
   - Parse the returned text/JSON to get an ETA in minutes when possible.

4. Combine everything in a clear final answer, for example:

   "Total price: 340 INR
    Kitchen prep time: 25 minutes
    Rider ETA: 12.2 minutes
    Approximate delivery completion time: ~37 minutes."

NO MAGIC ERROR MESSAGES:

- You MUST NOT say "the restaurant's tools are unresponsive"
  unless the JSON returned by restaurant_prep_tool includes an "error" field.
- If there is no "error" field in that JSON, assume the restaurant tools
  worked and use their price + prep time data.

Always try to call the tools again if the user rephrases or asks to retry,
instead of immediately giving up.
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
