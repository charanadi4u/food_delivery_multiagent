import logging

import click
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from resturant_executor import ResturantExecutor


from restaurant_agent import create_restaurant_agent

logger = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 9002

skill = AgentSkill(
        id='menu_and_prep',
        name='Get menu and prep time',
        description='A2A restaurant agent that uses MCP to handle menus, prices and prep times',
        tags=['restaurant', 'menu', 'prep_time'],
     )


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        name="restaurant_agent",
        description="A2A restaurant agent that uses MCP to handle menus, prices and prep times.",
        url=url,
        version="1.0.0",
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
       )


def main(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    load_dotenv()
    agent = create_restaurant_agent()

    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()
    memory_service = InMemoryMemoryService()

    runner = Runner(
    app_name="restaurant_agent",   # any stable string ID is fine
    agent=agent,
    session_service=session_service,
    artifact_service=artifact_service,
    memory_service=
    memory_service,
    )

    agent_executor = ResturantExecutor(runner, AgentCard)

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor, task_store=InMemoryTaskStore())

    url = f"http://{host}:{port}"
    card = build_agent_card(url)
    a2a_app = A2AStarletteApplication(agent_card=card, http_handler=request_handler)

    uvicorn.run(a2a_app.build(), host=host, port=port)


@click.command()
@click.option("--host", "host", default=DEFAULT_HOST)
@click.option("--port", "port", default=DEFAULT_PORT, type=int)
def cli(host: str, port: int) -> None:
    main(host, port)


if __name__ == "__main__":
    main()
