"""Learning analytics for strategies, trends, and recurring failures."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo

from salesforce_ai_engineer.reward_learning.models import (
    AgentLeaderboardEntry,
    AgentPerformanceMetric,
    FailurePattern,
    MetricType,
    PerformanceDashboard,
    PerformanceTrend,
    RewardScore,
    StrategyComparison,
    StrategyPerformance,
    StrategyRecommendation,
    StrategyType,
    WorkflowMetrics,
)

UTC = ZoneInfo("UTC")


class LearningAnalyzer:
    """Pure analytics component for learning from scored executions."""

    def build_strategy_performance(
        self,
        workflow_metrics: WorkflowMetrics,
        agent_metrics: dict[str, list[AgentPerformanceMetric]],
        execution_data: dict,
    ) -> list[StrategyPerformance]:
        """Summarize strategy effectiveness for participating agents."""

        now = datetime.now(UTC)
        strategies: list[StrategyPerformance] = []
        for agent_name, metrics in agent_metrics.items():
            agent_data = execution_data.get("agents", {}).get(agent_name, {})
            strategy = self._strategy_from(agent_data.get("strategy") or execution_data.get("strategy"))
            quality_scores = [
                self._normalize_metric(metric.value, metric.metric_type)
                for metric in metrics
                if metric.metric_type
                in {
                    MetricType.PLANNING_QUALITY,
                    MetricType.CODE_QUALITY,
                    MetricType.VERIFICATION_SCORE,
                    MetricType.TEST_COVERAGE,
                }
            ]
            success = bool(agent_data.get("success", workflow_metrics.is_workflow_successful))
            attempts = int(agent_data.get("attempts", workflow_metrics.total_retries + 1))
            execution_time = float(agent_data.get("execution_time", workflow_metrics.execution_time_seconds))
            strategies.append(
                StrategyPerformance(
                    strategy_type=strategy,
                    agent_name=agent_name,
                    total_uses=1,
                    successful_uses=1 if success else 0,
                    average_execution_time_seconds=execution_time,
                    average_retry_count=max(0.0, attempts - 1),
                    average_quality_score=mean(quality_scores) if quality_scores else workflow_metrics.code_quality_score,
                    success_rate=1.0 if success else 0.0,
                    confidence=0.65 + (0.2 if quality_scores else 0.0),
                    last_used_at=now,
                    updated_at=now,
                )
            )
        return strategies

    def detect_failure_patterns(
        self,
        workflow_id: str,
        execution_data: dict,
    ) -> list[FailurePattern]:
        """Detect recurring-looking failures within the completed workflow."""

        patterns: dict[tuple[str, str], FailurePattern] = {}
        agents = execution_data.get("agents", {})
        for agent_name, agent_data in agents.items():
            errors = agent_data.get("errors") or []
            if agent_data.get("error"):
                errors.append(agent_data["error"])
            for error in errors:
                category = self._categorize_failure(str(error))
                key = (agent_name, category)
                if key not in patterns:
                    patterns[key] = FailurePattern(
                        pattern_name=f"{category} in {agent_name}",
                        pattern_description=str(error),
                        agent_affected=agent_name,
                        failure_category=category,
                        occurrence_count=0,
                        success_count_with_recovery=0,
                        average_recovery_time_seconds=float(agent_data.get("recovery_time", 0.0)),
                        affected_workflows=[],
                        recommended_strategy=self._recommended_failure_strategy(category),
                        confidence=0.6,
                        pattern_severity=self._severity(category),
                    )
                pattern = patterns[key]
                pattern.occurrence_count += 1
                pattern.affected_workflows.append(workflow_id)
                if agent_data.get("successful_recoveries", 0) > 0:
                    pattern.success_count_with_recovery += 1
                pattern.confidence = min(1.0, 0.5 + pattern.occurrence_count * 0.15)
        return list(patterns.values())

    def recommend_strategies(
        self,
        current: list[StrategyPerformance],
        historical: list[StrategyPerformance],
    ) -> list[StrategyRecommendation]:
        """Recommend higher-performing strategies using recent and historical data."""

        recommendations: list[StrategyRecommendation] = []
        by_agent: dict[str, list[StrategyPerformance]] = defaultdict(list)
        for item in [*historical, *current]:
            by_agent[item.agent_name].append(item)

        for agent_name, items in by_agent.items():
            if not items:
                continue
            current_item = current[0] if len(current) == 1 else next(
                (item for item in current if item.agent_name == agent_name),
                items[-1],
            )
            best = max(items, key=self._strategy_score)
            current_score = self._strategy_score(current_item)
            best_score = self._strategy_score(best)
            if best.strategy_type == current_item.strategy_type or best_score <= current_score + 3:
                continue
            recommendations.append(
                StrategyRecommendation(
                    agent_name=agent_name,
                    current_strategy=current_item.strategy_type,
                    recommended_strategy=best.strategy_type,
                    improvement_potential=min(100.0, best_score - current_score),
                    justification=(
                        f"{best.strategy_type.value} has better historical effectiveness "
                        f"({best_score:.1f} vs {current_score:.1f})."
                    ),
                    historical_success_rate=best.success_rate,
                    confidence=min(best.confidence, 0.9),
                    estimated_time_savings_seconds=max(
                        0.0,
                        current_item.average_execution_time_seconds
                        - best.average_execution_time_seconds,
                    ),
                    estimated_quality_improvement_percent=max(
                        0.0,
                        best.average_quality_score - current_item.average_quality_score,
                    ),
                )
            )
        return recommendations

    def build_trends(
        self,
        scores: list[RewardScore],
        metric_type: MetricType = MetricType.WORKFLOW_SUCCESS,
        period: str = "all_time",
    ) -> list[PerformanceTrend]:
        """Build score trends for agents and workflows."""

        grouped: dict[tuple[str, str], list[RewardScore]] = defaultdict(list)
        for score in sorted(scores, key=lambda item: item.calculated_at):
            grouped[(score.entity_type, score.entity_id)].append(score)

        trends: list[PerformanceTrend] = []
        for (entity_type, entity_id), items in grouped.items():
            values = [item.score for item in items]
            timestamps = [item.calculated_at for item in items]
            direction, strength = self._trend_direction(values)
            trends.append(
                PerformanceTrend(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    metric_type=metric_type,
                    time_period=period,
                    trend_direction=direction,
                    trend_strength=strength,
                    values_over_time=values,
                    timestamps=timestamps,
                    average_value=mean(values),
                    min_value=min(values),
                    max_value=max(values),
                )
            )
        return trends

    def build_leaderboard(
        self,
        scores: list[RewardScore],
        trends: list[PerformanceTrend],
        period: str = "all_time",
    ) -> list[AgentLeaderboardEntry]:
        """Generate agent leaderboard entries."""

        agent_scores: dict[str, list[RewardScore]] = defaultdict(list)
        for score in scores:
            if score.entity_type == "agent":
                agent_scores[score.entity_id].append(score)

        trend_by_agent = {
            trend.entity_id: trend.trend_direction
            for trend in trends
            if trend.entity_type == "agent"
        }
        entries: list[AgentLeaderboardEntry] = []
        for agent_name, items in agent_scores.items():
            factor_values = defaultdict(list)
            for item in items:
                for factor, value in item.factors.items():
                    factor_values[factor].append(value)
            success_rate = mean(factor_values["workflow_success"]) / 100 if factor_values["workflow_success"] else mean(item.score for item in items) / 100
            entries.append(
                AgentLeaderboardEntry(
                    rank=0,
                    agent_name=agent_name,
                    overall_score=mean(item.score for item in items),
                    workflows_completed=len(items),
                    average_execution_time_seconds=max(
                        0.0,
                        3600.0 * (1.0 - mean(factor_values["execution_time"]) / 100),
                    )
                    if factor_values["execution_time"]
                    else 0.0,
                    success_rate=max(0.0, min(1.0, success_rate)),
                    quality_score=mean(factor_values["code_quality"]) if factor_values["code_quality"] else mean(item.score for item in items),
                    recovery_effectiveness=mean(factor_values["recovery_effectiveness"]) / 100 if factor_values["recovery_effectiveness"] else 1.0,
                    trend_indicator=trend_by_agent.get(agent_name, "stable"),
                    period=period,
                )
            )
        entries.sort(key=lambda item: item.overall_score, reverse=True)
        for index, entry in enumerate(entries, start=1):
            entry.rank = index
        return entries

    def compare_strategies(
        self,
        baseline: StrategyPerformance,
        candidate: StrategyPerformance,
    ) -> StrategyComparison:
        """Compare two strategy performance profiles."""

        baseline_score = self._strategy_score(baseline)
        candidate_score = self._strategy_score(candidate)
        delta = candidate_score - baseline_score
        return StrategyComparison(
            agent_name=baseline.agent_name,
            baseline_strategy=baseline.strategy_type,
            candidate_strategy=candidate.strategy_type,
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            score_delta=delta,
            confidence_delta=candidate.confidence - baseline.confidence,
            recommendation="adopt_candidate" if delta > 3 else "keep_baseline",
        )

    def build_dashboard(
        self,
        scores: list[RewardScore],
        trends: list[PerformanceTrend],
        strategies: list[StrategyPerformance],
        failures: list[FailurePattern],
        recommendations: list[StrategyRecommendation],
        period: str = "all_time",
    ) -> PerformanceDashboard:
        """Build a dashboard snapshot from learning history."""

        workflow_scores = [score for score in scores if score.entity_type == "workflow"]
        success_scores = [score.factors.get("reliability", score.score) for score in workflow_scores]
        return PerformanceDashboard(
            period=period,
            total_workflows=len(workflow_scores),
            average_workflow_score=mean(score.score for score in workflow_scores) if workflow_scores else 0.0,
            workflow_success_rate=mean(success_scores) / 100 if success_scores else 0.0,
            leaderboard=self.build_leaderboard(scores, trends, period),
            top_strategies=sorted(strategies, key=self._strategy_score, reverse=True)[:10],
            recurring_failures=sorted(failures, key=lambda item: item.occurrence_count, reverse=True)[:10],
            recommendations=recommendations[:10],
            trends=trends[:20],
        )

    def _strategy_score(self, item: StrategyPerformance) -> float:
        retry_penalty = min(20.0, item.average_retry_count * 5.0)
        time_penalty = min(20.0, item.average_execution_time_seconds / 180.0)
        return max(
            0.0,
            min(
                100.0,
                (item.success_rate * 45.0)
                + (item.average_quality_score * 0.4)
                + (item.confidence * 15.0)
                - retry_penalty
                - time_penalty,
            ),
        )

    def _trend_direction(self, values: list[float]) -> tuple[str, float]:
        if len(values) < 2:
            return "stable", 0.0
        delta = values[-1] - values[0]
        spread = max(values) - min(values)
        strength = 0.0 if spread == 0 else min(1.0, abs(delta) / spread)
        if abs(delta) < 2.0:
            return "stable", strength
        return ("improving" if delta > 0 else "declining"), strength

    def _normalize_metric(self, value: float, metric_type: MetricType) -> float:
        if metric_type in {MetricType.EXECUTION_TIME, MetricType.RETRY_COUNT, MetricType.RESOURCE_USAGE}:
            return max(0.0, 100.0 - value)
        return value * 100 if value <= 1 else value

    def _strategy_from(self, value: object) -> StrategyType:
        if isinstance(value, StrategyType):
            return value
        if isinstance(value, str):
            normalized = value.lower().strip()
            for strategy in StrategyType:
                if strategy.value == normalized:
                    return strategy
        return StrategyType.STANDARD

    def _categorize_failure(self, error: str) -> str:
        lowered = error.lower()
        if "timeout" in lowered:
            return "timeout"
        if "permission" in lowered or "auth" in lowered:
            return "permission"
        if "deploy" in lowered:
            return "deployment"
        if "test" in lowered or "verify" in lowered:
            return "verification"
        if "connection" in lowered or "network" in lowered:
            return "network"
        return "unknown"

    def _recommended_failure_strategy(self, category: str) -> StrategyType:
        return {
            "timeout": StrategyType.RETRY,
            "network": StrategyType.RETRY,
            "permission": StrategyType.CONSERVATIVE,
            "deployment": StrategyType.ROLLBACK,
            "verification": StrategyType.REGENERATE,
        }.get(category, StrategyType.FALLBACK)

    def _severity(self, category: str) -> str:
        return {
            "permission": "high",
            "deployment": "critical",
            "verification": "high",
            "timeout": "medium",
            "network": "medium",
        }.get(category, "low")
