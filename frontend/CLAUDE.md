# Frontend instructions

This is the web UI for a federated-learning DDoS detection demo.
Before changing anything, read:
1. `../docs/frontend-brief.md` for the idea, screens and behaviour.
2. `../docs/api-contract.md` for the API. Build against it, including the 🔜 planned parts.
3. `../docs/mockup/fl-flow-mockup.html` for the target look and animation (open it in a browser).

Rules
- Stack: React + Vite (already set up). Call the backend only through `import.meta.env.VITE_API_URL`.
- Do not edit backend files (`../api`, `../*.py`, Dockerfile, docker-compose.yml). If you need data that the contract lacks, say so and propose a contract change.
- Render N clients from API data, never a hardcoded 3.
- Animate from real round data returned by the API, not from timers.
