# Hardware Foundry

LLM multi-agent platform that turns natural-language hardware ideas
(*"I want a smart desk lamp with BLE dimming"*) into manufacturable artifacts:
**BOM, 3D-print files, KiCad PCB, ESP32 firmware, companion App, assembly docs.**

Built on the architecture defined in `~/.claude/plans/rustling-coalescing-eclipse.md`.

---

## Status

**Phase 0** — baseline infrastructure scaffold. 11/11 foundation files in place.
- Monorepo directory tree (53 dirs)
- uv workspace root
- Docker Compose stack (Postgres / Redis / Qdrant / MinIO / LiteLLM / Langfuse)
- LiteLLM routing config
- `foundry_agent_base` package: `ProductState`, `BaseAgent`

Next turn: FastAPI app, LangGraph main pipeline, Next.js frontend, Echo Agent.

---

## Quickstart

### 1. Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | `brew install python@3.12` |
| uv | 0.10+ | already installed (`uv --version`) |
| Docker / OrbStack | recent | `brew install orbstack` then launch app |
| Node | 20+ | `brew install node` (needed in next phase) |

### 2. Bootstrap

```bash
cd ~/Projects/hardware-foundry

cp .env.example .env
$EDITOR .env       # at minimum, set ANTHROPIC_API_KEY

uv sync            # creates .venv, resolves workspace

cd infra
docker compose --env-file ../.env up -d
docker compose ps  # should show all services healthy
```

Open:
- LiteLLM:   http://localhost:4000/health
- Langfuse:  http://localhost:3001
- MinIO:     http://localhost:9001  (`minioadmin` / `minioadmin`)
- Qdrant:    http://localhost:6333/dashboard

### 3. Smoke test (Phase 0)

```bash
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-litellm-master-dev" \
  -H "Content-Type: application/json" \
  -d '{"model":"agent:echo","messages":[{"role":"user","content":"ping"}]}'
```

A 200 with text content confirms the LLM gateway works end-to-end.

### 4. Tear down

```bash
cd infra && docker compose down       # keep volumes
cd infra && docker compose down -v    # nuke volumes (fresh start)
```

---

## Project layout

See plan §3 for the full tree. Key entry points:

```
agents/_base/foundry_agent_base/
  state.py     # single source of truth: ProductState + all sub-schemas
  agent.py     # BaseAgent abstract; every agent inherits

infra/
  docker-compose.yml   # Phase 0 stack
  litellm/config.yaml  # agent virtual name -> model routing
```

---

## Roadmap

12-phase plan, ~9 months self-paced. See plan file §五 for details.

| Phase | Scope | Demo |
|---|---|---|
| 0  | Infra + Hello World | scaffold (current) |
| 1  | Clarifier + Reference + Planner | sentence -> ProductSpec |
| 2  | Compliance + Feasibility | ProductSpec -> market gates + budget |
| 3  | Component Selection | ProductSpec -> BOM |
| 4  | CAD + DfAM | BOM -> STL + DfAM report |
| 5  | PCB | BOM -> Gerber + ERC/DRC |
| 6  | Simulation | Schematic -> SPICE results |
| 7  | Firmware + App | ESP32 BLE dimming + Expo app |
| 8  | Review (5-critic debate) | Approve / Reject decision |
| 9  | Fabrication | JLCPCB order package + OctoPrint job |
| 10 | Assembly + Test + Manual docs | PDF delivery bundle |
| 11 | E2E + Benchmark + Real lamp | Physical lamp shipped |
| 12 | SaaS readiness | Auth.js multi-tenant, K3s, billing |

---

## License

TBD.
