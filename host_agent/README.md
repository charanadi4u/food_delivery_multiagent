# Host Agent (Food Delivery Orchestrator)

This is a small Gradio-based UI that talks to the RoutingAgent (an ADK agent)
which in turn delegates work to the remote A2A agents:

- `rider_agent` (for ETA and routing via Maps MCP)
- `restaurant_agent` (for menus and prep times via DB MCP)

1. Create a `.env` using `example.env`.
2. Make sure rider_agent and restaurant_agent are running.
3. Run:

   ```bash
   uv run python -m host_agent
   ```

4. Open the Gradio URL shown in the console.
