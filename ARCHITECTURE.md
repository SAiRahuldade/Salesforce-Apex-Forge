# Project Architecture and Verification

## Overview
This document summarizes the project's architecture, agent implementations, frameworks and dependencies, external integrations, test suites (unit, integration, performance), deployment components, and a verification checklist.

## Agents (implementations and paths)
- `project_agent.py` — Root orchestrator and entrypoint.
- `src/salesforce_ai_engineer/agent/` and subpackages:
  - `deployment/agent.py` — DeploymentAgent orchestration and CLI helpers.
  - `recovery/agent.py` — RecoveryAgent for failure handling.
  - `salesforce_engineer/agent.py` — Core engineer agent logic.
  - `verifier/agent.py` — VerifierAgent for verification workflows.

## Frameworks & Key Dependencies
- Python project managed by `pyproject.toml` and `requirements.txt`.
- Notable libraries: FastAPI, Uvicorn, LangChain, Ollama, Pydantic, SQLAlchemy, Typer, OpenAI client.
- Config files: `config/settings.yaml`, `config/settings.example.toml`.

## External Integrations
- Ollama / local LLMs — referenced in `config/settings.yaml`.
- OpenAI and other LLM providers through adapter code in `src/*`.
- Salesforce integrations under `src/salesforce_ai_engineer/*` (auth, APIs, deployment hooks).

## Test Suites and Locations
- Unit & integration tests: `tests/` (many subpackages). Key groups:
  - `tests/agent/` — orchestrator, planner, registry tests.
  - `tests/api/` — API endpoint tests.
  - `tests/core/`, `tests/db/`, `tests/deployment/`, `tests/integration/`, `tests/memory/`, `tests/workflow/`, etc.
- Performance tests: `tests/performance/` (load testing, benchmarking scripts).
- NVIDIA NIM tests: `nvidia-nim-chat/tests/`.
- Test artifacts: `test_output.txt`, `test_perf.txt` contain recent run outputs.

## Deployment & CI/CD
- Deployment orchestration code lives in `src/salesforce_ai_engineer/deployment/` (agents, executor, monitor, rollback).
- Scripts: `scripts/list_models.py` for model inventory.
- CI/CD configs (GitHub Actions, Dockerfiles, Kubernetes manifests) were not found in the repo; add them to enable automated pipelines.

## Performance Testing & Benchmarks
- `tests/performance/test_load_testing.py` — load tests and resource profiling.
- Integration benchmarks in `tests/integration/` e.g., engine performance benchmarks.
- Memory/agent performance measured in `tests/memory/test_agent_integration.py`.

## How to run tests (recommended)
1. Activate the venv in the workspace root.

```powershell
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned)
& ".venv\Scripts\Activate.ps1"
```

2. Install dependencies (if needed):

```powershell
python -m pip install -r requirements.txt
```

3. Run the full test suite (pytest):

```powershell
pytest -q
```

4. Run performance tests separately:

```powershell
pytest tests/performance -q
```

## Verification Checklist
- [ ] Unit tests: all pass (`pytest tests --maxfail=1`).
- [ ] Integration tests: end-to-end flows pass (`pytest tests/integration`).
- [ ] Performance: benchmarks meet service-level targets (`tests/performance`).
- [ ] Deployment: `src/salesforce_ai_engineer/deployment` scripts execute a dry-run successfully.
- [ ] Agent integrations: `nvidia-nim-chat` and LLM adapters respond in integration tests.
- [ ] Test artifacts: confirm `test_output.txt` and `test_perf.txt` reflect successful runs.

