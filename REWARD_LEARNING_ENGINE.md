# Reward & Learning Engine

The Reward & Learning Engine evaluates completed workflows and participating
agents without fine-tuning models or modifying provider weights. It learns from
execution history by producing deterministic reward scores, analytics, trends,
failure patterns, and strategy recommendations that future workflows can query.

## Architecture

- `RewardLearningEngine` is the facade used by the orchestrator and application
  services.
- `WorkflowEvaluator` extracts workflow and agent metrics from completed
  execution reports or explicit execution data.
- `RewardScorer` applies configurable weighted scoring policies and confidence
  scoring.
- `LearningAnalyzer` detects trends, compares strategies, builds leaderboards,
  detects failure patterns, and produces dashboards.
- `RewardLearningRepository` persists all learning artifacts through the Memory
  Agent using `REWARD_RECORD` and `EXECUTION_METRIC` records.
- `EventBus` publishes traceable learning lifecycle events including
  `reward_learning.evaluation.started`, `reward.updated`, and
  `reward_learning.evaluation.completed`.

## Integration

The orchestrator accepts an optional `reward_learning_engine`. When configured,
every completed workflow report is evaluated automatically. Learning failures
are isolated from workflow success and are emitted as
`orchestrator.workflow.learning_failed`.

The default container wires the engine with the existing `MemoryManager` and
`EventBus`, so API and CLI entry points inherit automatic learning.

## Metrics

The engine evaluates:

- planning quality
- code quality
- verification score
- deployment success
- recovery effectiveness
- execution time
- retry count
- test coverage
- resource usage
- workflow success

Scores are explainable through each `RewardScore.factors`,
`RewardScore.weights`, and the `LearningEvaluationResult.trace` payload.

## Future Adaptation

Future reinforcement learning, semantic memory, adaptive planning, or vector
retrieval can consume the same persisted records and strategy recommendations.
No existing agent contract needs to change because the engine sits behind the
orchestrator and memory/event interfaces.
