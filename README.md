# AI Pair Engineer

> An AI-assisted backend engineering workspace. Not a code review tool — an engineering teammate.

Built for backend engineers working on distributed systems, platform services, and reliability-critical implementations. The product is designed to feel like a senior engineering colleague giving focused guidance before a PR review, not a static analysis dashboard.

---

## What It Does

AI Pair Engineer helps backend engineers improve implementations before human PR review by providing:

- **Architecture Coaching** — service boundaries, ownership patterns, coupling and evolution
- **Reliability Guidance** — timeouts, retries, idempotency, partial failure scenarios
- **Test Design Suggestions** — high-signal coverage, edge cases, failure-mode tests
- **Refactor Recommendations** — maintainability wins, readability, change isolation
- **PR Readiness Analysis** — what a reviewer needs to trust the implementation

The assistant speaks like a senior backend engineer, not a compliance tool.

---

## Architecture

<img width="1920" alt="AI Pair Engineer — Architecture" src="https://github.com/user-attachments/assets/9ffb7c75-0f9f-4266-8c39-8cdc462b655f" />

**Current stack:**

| Layer | Technology |
|---|---|
| Frontend | Streamlit 1.36+ with custom CSS workspace |
| Orchestration | Python — `review_engine.py` |
| Prompt engineering | LangChain `ChatPromptTemplate` — `prompts.py` |
| LLM | Google Gemini via `langchain-google-genai` |
| Package management | `uv` with locked dependencies |

---

## Potential Production Extensions

> **None of the following are implemented in the current POC.**
> Included to demonstrate systems thinking and a clear product roadmap.

| Extension | Purpose |
|---|---|
| **RAG Layer** | Retrieve org-specific coding standards, past review decisions, and incident history |
| **MCP Integration** | Connect to live repository context via Model Context Protocol |
| **Multi-Agent Collaboration** | Run parallel specialist agents (architecture, reliability, test) simultaneously |
| **Organizational Knowledge Base** | Persistent memory of team engineering decisions and patterns |
| **Repository Context Retrieval** | Index and retrieve patterns from the full codebase via vector search |
| **Coding Standards Retrieval** | Enforce org-specific style guides and conventions at review time |

These extensions would evolve the current LLM-per-request model into a retrieval-augmented, context-aware engineering assistant with organizational memory.

---

## Preloaded Engineering Scenarios

Three realistic backend scenarios are included in `sample_projects/`, each containing intentional engineering flaws:

| Scenario | System Type | Key Concerns |
|---|---|---|
| **Payment Orchestrator Service** | Async API, external dependencies, money movement | Idempotency, retry handling, distributed consistency |
| **Ride Dispatch Worker** | Queue worker, concurrent allocation, state contention | Race conditions, backpressure, worker safety |
| **Notification Aggregation Service** | Fanout service, provider retries, partial failure | Retry strategy, async throughput, dead letters |

Each scenario is designed to surface realistic engineering flaws across architecture, reliability, observability, and testability dimensions.

---

## Assistant Modes

| Mode | Focus |
|---|---|
| **Architecture Coach** | Service design, boundaries, coupling, evolution paths |
| **Reliability Advisor** | Retry logic, timeouts, idempotency, partial failure |
| **Test Designer** | Test strategy, coverage, edge cases, failure-mode tests |
| **Refactor Assistant** | Readability, maintainability, change isolation |
| **PR Readiness** | Completeness, observability, reviewer context |
| **Full Engineering Review** | All five perspectives in a single pass |

---

## Local Setup

**Requirements:** Python 3.10+, [uv](https://docs.astral.sh/uv/)

```bash
uv venv
uv sync
```

Create a local environment file:

```bash
cp .env.example .env
```

Edit `.env` with your Gemini API key:

```
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash
```

Run the app:

```bash
uv run streamlit run app.py
```

---

## Streamlit Cloud Deployment

1. Push this repository to GitHub — `.env` and `.venv/` are excluded by `.gitignore`
2. Connect the repository in [Streamlit Cloud](https://streamlit.io/cloud)
3. In **Settings → Secrets**, paste the following TOML (see `.streamlit/secrets.toml.example`):

```toml
GOOGLE_API_KEY = "your-gemini-api-key-here"
GEMINI_MODEL = "gemini-1.5-flash"
```

The app reads from `st.secrets` first (Streamlit Cloud), then falls back to the local `.env` file.

---

## Key Engineering Decisions

**Why Streamlit?**
Fastest path from LLM output to an interactive, editable workspace. The goal was a polished engineering demo, not a production frontend framework exercise.

**Why LangChain?**
Clean prompt templating and a stable abstraction over Gemini's API. Makes mode-specific prompt engineering explicit and testable.

**Why Gemini?**
Strong code comprehension and instruction-following at low latency. The `gemini-1.5-flash` model balances speed and quality for iterative review workflows.

**Why uv?**
Reproducible, fast dependency resolution with a locked `uv.lock`. Consistent installs across developer machines and CI.

**Why no RAG, MCP, or multi-agent systems?**
This POC demonstrates engineering judgment and product thinking — not framework complexity. The architecture is intentionally lightweight so the engineering guidance quality and UX polish are the signal, not the infrastructure.

---

## Project Structure

```
ai-pair-engineer/
├── app.py                    # Streamlit UI and workspace logic
├── review_engine.py          # AI review orchestration (Gemini via LangChain)
├── prompts.py                # Mode-specific prompt templates
├── sample_projects/          # Preloaded engineering scenarios
│   ├── payment_orchestrator_service.py
│   ├── ride_dispatch_worker.py
│   └── notification_aggregation_service.py
├── diagrams/                 # Architecture and workflow diagrams
├── .streamlit/
│   ├── config.toml           # Theme and server config
│   └── secrets.toml.example  # Secrets template for Streamlit Cloud
├── .env.example              # Environment variable template
├── pyproject.toml            # Dependencies (uv)
└── uv.lock                   # Locked dependency graph
```
