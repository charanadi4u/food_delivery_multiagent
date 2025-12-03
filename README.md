# Food Delivery Multi-Agent (A2A + MCP + Google ADK)

how to build a food delivery orchestration system using:

- Google ADK agents
- A2A protocol for agent-to-agent communication
- MCP servers for:
  - Restaurant / menu / DB (Postgres)
  - Rider / ETA via Google Maps Directions API

---

## Architecture Diagrams

### 1. End-to-end multi-agent architecture

![Food Delivery Multi-Agent Architecture](./food_delivery_architecture.png)

This diagram shows how the end user, host agent (Gradio UI + RoutingAgent),
remote A2A agents, MCP servers, Google Routes API, and Postgres all connect.

### 2. Host Agent / Gradio UI

![Food Delivery Host Agent UI](./food_delivery_agent.PNG)

This captures the Gradio front-end where the user interacts with the
Food Delivery Host Agent and sees combined responses (price, prep time, ETA).

### 3. Alternative Host / Flow View

![Food Delivery Host Agent – Alternative View](./food_delivery_agent_1.PNG)

This diagram/screenshot provides an alternate view of the host agent or
flow that you can use in presentations or documentation.

---

## Components

- `host_agent/` – ADK routing agent + Gradio UI that delegates to remote agents over A2A
- `restaurant_agent/` – A2A agent backed by an ADK agent + MCP DB server
- `rider_agent/` – A2A agent backed by an ADK agent + MCP Maps server

## High-level run order

1. Start Postgres and create a database (e.g. `food_delivery`).
2. Configure each folder's `.env` from its `example.env`.
3. Start MCP servers (DB + Maps) implicitly – the ADK agents will spawn them
   via `MCPToolset` using stdio.
4. Start the remote restaurant A2A agents:
   - `cd restaurant_agent`
   - `uv run .`
5. Start the remote restaurant A2A agents:
   - `cd ride_agent`
   - `uv run .`
5. Start the host UI:
   - `cd host_agent`
   - `uv run .`
6. Interact via the Gradio UI and watch it route work between agents.
