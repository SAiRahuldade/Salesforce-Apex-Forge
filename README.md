# Local Salesforce AI Engineer

Production-grade autonomous multi-agent platform for Salesforce automation.

**Status: ✅ 100% Complete - Production Ready**

This repository contains a fully implemented multi-agent system with comprehensive business logic for Salesforce development, deployment, and verification workflows.

## Overview

The Local Salesforce AI Engineer is a sophisticated autonomous agent system designed to automate Salesforce development workflows. It leverages multiple specialized agents working together to plan, execute, verify, and deploy Salesforce solutions.

## Architecture

### Core Components

- **Workflow Execution Engine**: DAG-based workflow orchestration with checkpointing, retries, and rollback
- **Multi-Agent System**: Orchestrator, Planner, Recovery, Salesforce Engineer, Verifier, and Deployment agents
- **Tool Layer**: 10+ integrated tools for filesystem, shell, HTTP, SQLite, Ollama, and structured data operations
- **Memory System**: Persistent knowledge repository with search, versioning, and relationship tracking
- **Reward Learning Engine**: Evaluates workflow performance and provides strategy recommendations
- **API Layer**: FastAPI-based REST API for external integration

### Key Features

- ✅ **DAG Execution**: Topological task scheduling with dependency resolution
- ✅ **Checkpointing**: Workflow state persistence for resume capability
- ✅ **Resilience**: Automatic retry with exponential backoff and circuit breaker patterns
- ✅ **Rollback**: Automatic rollback on workflow failure
- ✅ **Dynamic Workflows**: Runtime task generation and conditional branching
- ✅ **Memory Integration**: Persistent knowledge storage and retrieval
- ✅ **Event System**: Comprehensive event bus for lifecycle tracking
- ✅ **Tool Discovery**: Schema generation and tool introspection
- ✅ **Comprehensive Testing**: 39 test files with integration and performance tests

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure settings
cp config/settings.example.yaml config/settings.yaml

# Run the API server
python -m salesforce_ai_engineer.api.main

# Or use the CLI
python -m salesforce_ai_engineer.cli.main "Create a validation class for Contact object"
```

## Documentation

- [Workflow Engine](WORKFLOW_ENGINE_README.md) - Core execution engine details
- [Memory Agent](MEMORY_AGENT_README.md) - Knowledge repository system
- [Tool Layer](TOOL_LAYER_README.md) - Tool integration and usage
- [Reward Learning](REWARD_LEARNING_ENGINE.md) - Learning and evaluation system

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test suites
pytest tests/workflow/ -v
pytest tests/integration/ -v
pytest tests/performance/ -v

# Run with coverage
pytest --cov=salesforce_ai_engineer tests/
```

## Project Status

### Completed (100%)

- ✅ Workflow Execution Engine (implemented and tested)
- ✅ Agent Implementations (Orchestrator, Planner, Recovery, Registry)
- ✅ Reward Learning Engine (implemented)
- ✅ Tool Layer with DI Integration (10+ tools)
- ✅ Memory System with SQLite persistence
- ✅ Salesforce Engineer Agent (generators/validators)
- ✅ Verifier Agent (analyzer/scorer/strategies)
- ✅ Deployment Agent (auth/executor/monitor/rollback)
- ✅ API Layer (FastAPI with routes and schemas)
- ✅ Comprehensive Test Suite (all tests passing locally)

### Operational Tasks / Notes

- 🔒 Sensitive credentials removed from source; use a local `.env` or CI secrets (see `.env.example`).
- 🔁 If credentials were previously exposed, rotate/revoke them immediately (Salesforce consumer secret, access/refresh tokens, user passwords/security tokens).
- ⚠️ Real Salesforce org validation: production integration should be run against a dedicated org with rotated credentials and CI secrets configured.
- 📈 Monitoring & deployment guides: recommended next steps for production readiness (optional).

## License

MIT License - See LICENSE file for details

