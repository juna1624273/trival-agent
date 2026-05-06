# Trival Agent — Intelligent Travel Planning System

A multi-agent travel planning system built on **LangGraph** and the **MCP (Model Context Protocol)**, powered by LLMs for automated itinerary generation with human-in-the-loop feedback.

## Features

- **Intelligent Planning** — Decomposes complex travel requests into structured, dependency-aware execution steps
- **Multi-Agent Collaboration** — 1 orchestrator + 6 domain-specific sub-agents (Transport, Maps, Weather, Hotel, Search, File)
- **ReAct Reasoning** — Each sub-agent runs a Think-Act-Observe loop with tool calling for grounded decisions
- **Dependency-Aware Parallel Execution** — Steps without interdependencies run concurrently via `asyncio.gather`
- **Human-in-the-Loop** — LLM autonomously detects missing information and pauses for user input via LangGraph `interrupt()`
- **Incremental Feedback** — Users can refine specific steps; the system identifies affected steps and regenerates only those
- **Smart Caching** — Two-tier cache (exact-match + semantic via ChromaDB) reduces redundant LLM and API calls
- **Context Management** — Automatic message window compression to stay within token budgets
- **Graceful Degradation** — MCP servers are optional; falls back to direct REST APIs with circuit breakers
- **PDF Export** — Professional itinerary PDF with Chinese font support and Amap static maps
- **SSE Streaming** — Real-time progress updates to the frontend via Server-Sent Events
- **Multi-Model Support** — Pluggable LLM backend: DeepSeek, Qwen (Tongyi), Kimi (Moonshot), OpenAI

## Architecture

```
User Query → Plan → Execute (parallel) → Replan → Finalize → Itinerary
                 ↑        ↓                   ↑
                 └────────┴───────────────────┘
                          Human Input
```

### Agents

| Agent | Type | Responsibilities |
|-------|------|-----------------|
| **Orchestrator** | parent | Task decomposition, step coordination, final synthesis |
| **Transport** | transport | Flights, trains, bus route queries |
| **Maps** | maps | Geocoding, POI search, directions |
| **Weather** | weather | Forecasts, warnings, travel advisories |
| **Hotel** | hotel | Accommodation search and comparison |
| **Search** | search | Attractions, restaurants, guides |
| **File** | file | PDF/Excel document export |

### MCP + API Fallback Layer

The system uses a dual-layer service architecture:

- **Layer 1** — MCP protocol for standardized tool calls (Amap, Railway, Flight, Weather, Hotel, Search)
- **Layer 2** — Direct REST API fallback when MCP servers are unavailable (Amap API, OpenWeatherMap, Tavily, DuckDuckGo)

## Quick Start

### Prerequisites

- Python 3.10+
- Redis (optional, for distributed caching)

### Installation

```bash
git clone https://github.com/juna1624273/trival-agent.git
cd trival-agent
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Essential environment variables:

```env
# LLM Provider (choose one)
LLM_PROVIDER=deepseek          # deepseek | qwen | kimi | openai
LLM_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=sk-xxx

# External APIs
AMAP_API_KEY=xxx                # Amap (高德地图) for maps & POI
WEATHER_API_KEY=xxx             # OpenWeatherMap
SEARCH_API_KEY=xxx              # Tavily Search

# Optional: MCP server endpoints (default 127.0.0.1:8100-8105)
AMAP_MCP_URL=http://127.0.0.1:8100/mcp
RAILWAY_MCP_URL=http://127.0.0.1:8101/mcp
# ... see full .env for all options
```

### Run

```bash
# Start the backend server
python -m src.main

# Or with uvicorn
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://127.0.0.1:8000/** in your browser.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/plan` | Create a new planning session |
| GET | `/api/v1/plan/{id}/stream` | SSE stream for real-time progress |
| GET | `/api/v1/plan/{id}/status` | Check plan execution status |
| POST | `/api/v1/plan/{id}/resume` | Resume after human interruption |
| POST | `/api/v1/plan/{id}/feedback` | Submit incremental feedback |
| DELETE | `/api/v1/plan/{id}` | Cancel a planning session |
| GET | `/api/v1/plan/{id}/export/pdf` | Export itinerary as PDF |
| GET | `/api/v1/models` | List available LLM model presets |
| GET | `/health` | Health check |

Full API documentation at **http://127.0.0.1:8000/docs** (Swagger UI).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Framework** | FastAPI + Uvicorn |
| **Graph Engine** | LangGraph + LangChain |
| **Protocol** | MCP (Model Context Protocol) |
| **LLMs** | DeepSeek V4, Qwen, Kimi, GPT-4o (OpenAI-compatible) |
| **Vector Store** | ChromaDB |
| **Caching** | Redis + in-memory |
| **Frontend** | Vanilla HTML5 + CSS3 + JavaScript (SPA) |
| **PDF** | ReportLab |
| **Testing** | Pytest + pytest-asyncio |

## Project Structure

```
trival-llm/
├── src/
│   ├── main.py                  # FastAPI entry point
│   ├── config/settings.py       # Configuration & model presets
│   ├── graph/                   # LangGraph StateGraph workflow
│   │   ├── state.py             # State definition
│   │   ├── builder.py           # Graph builder (plan→execute→replan→finalize)
│   │   ├── conditions.py        # Conditional routing
│   │   └── nodes/               # Node implementations
│   ├── agents/base.py           # Base agent + 6 sub-agent classes
│   ├── llm/                     # LLM provider, prompts, structured output
│   ├── mcp/                     # MCP client, tool registry, API fallback
│   ├── memory/                  # Vector store, cache coordinator, context manager
│   ├── api/                     # Routes, middleware, dependency injection
│   ├── interaction/             # Human-in-the-loop manager
│   └── utils/                   # JSON parser, PDF generator, event bus
├── frontend/                    # SPA with 4 tabs (Chat, Plan, Itinerary, Settings)
├── tests/                       # Unit & integration tests
├── data/                        # ChromaDB persistence & itinerary exports
├── mcp.json                     # MCP server configuration
└── requirements.txt
```

## Supported Models

- **DeepSeek**: V4 Flash, V4 Pro, V3, R1
- **Qwen (通义千问)**: Plus, Max, Turbo
- **Kimi (Moonshot)**: 8K, 32K, 128K
- **OpenAI**: GPT-4o, GPT-4o Mini

## License

MIT License
