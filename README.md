# Food Delivery Multi-Agent (A2A + MCP + Google ADK)

This project is inspired by the `airbnb_planner_multiagent` sample and shows
how to build a food delivery orchestration system using:

- Google ADK agents
- A2A protocol for agent-to-agent communication
- MCP servers for:
  - Restaurant / menu / DB (Postgres)
  - Rider / ETA via Google Maps Directions API

## Components

- `host_agent/` – ADK routing agent + Gradio UI that delegates to remote agents over A2A
- `restaurant_agent/` – A2A agent backed by an ADK agent + MCP DB server
- `rider_agent/` – A2A agent backed by an ADK agent + MCP Maps server

## High-level run order

1. Start Postgres and create a database (e.g. `food_delivery`).
2. Configure each folder's `.env` from its `example.env`.
3. Start MCP servers (DB + Maps) implicitly – the ADK agents will spawn them
   via `MCPToolset` using stdio.
4. Start the remote A2A agents:
   - `python -m restaurant_agent`
   - `python -m rider_agent`
5. Start the host UI:
   - `cd host_agent`
   - `python -m host_agent`
6. Interact via the Gradio UI and watch it route work between agents.
