from collections.abc import Callable

import httpx

from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    SendMessageRequest,
    SendMessageResponse,
)
from dotenv import load_dotenv


load_dotenv()


class RemoteAgentConnection:
    """Thin wrapper around A2AClient for a specific remote agent."""

    def __init__(self, agent_url: str, agent_card: AgentCard):
        print(f"Connecting to remote agent at: {agent_url}")
        self._httpx_client = httpx.AsyncClient(timeout=30)
        self.agent_client = A2AClient(self._httpx_client, agent_card, url=agent_url)
        self.card = agent_card

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(self, message_request: SendMessageRequest) -> SendMessageResponse:
        return await self.agent_client.send_message(message_request)
