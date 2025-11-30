import logging

import click
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from ride_executor import RideExecutor

from rider_agent import create_rider_agent

logger = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 9001

skill = AgentSkill(
        id='assign_and_eta',
        name='Assign rider and compute ETA',
        description='Compute travel distance and ETA between restaurant and customer.',
        tags=['rider', 'eta', 'route'],
     )

def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        name="rider_agent",
        description="Rider A2A agent that uses MCP to compute ETAs and routes.",
        url=url,
        version="1.0.0",
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
        )

def main(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    load_dotenv()
    agent = create_rider_agent()

    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()
    memory_service = InMemoryMemoryService()

    runner = Runner(
        app_name="rider_agent",   # any stable string ID is fine
        agent=agent,
        session_service=session_service,
        artifact_service=artifact_service,
        memory_service=memory_service,
    )

    agent_executor = RideExecutor(runner, AgentCard)

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
