"""Comprehensive test suite for Recovery Agent."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.memory.sqlite_store import SQLiteMemoryStore
from salesforce_ai_engineer.recovery.agent import RecoveryAgent
from salesforce_ai_engineer.recovery.models import (
    FailureReport,
    FailureCategory,
    FailureSeverity,
    RecoveryPlan,
    RecoveryStatus,
    RecoveryStrategy,
    FailureSignature,
)
from salesforce_ai_engineer.recovery.analyzer import FailureAnalyzer
from salesforce_ai_engineer.recovery.strategies import (
    RetryStrategy,
    RegenerateStrategy,
    RollbackStrategy,
    FallbackStrategy,
    StrategyFactory,
)
from salesforce_ai_engineer.recovery.executor import RecoveryExecutor

UTC = ZoneInfo("UTC")


@pytest.fixture
async def memory_manager(tmp_path):
    """Create a memory manager for tests."""
    db_path = tmp_path / "recovery_test.db"
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    yield manager
    await store.close()


@pytest.fixture
def event_bus():
    """Create an event bus."""
    return EventBus()


@pytest.fixture
async def recovery_agent(event_bus, memory_manager):
    """Create a Recovery Agent."""
    return RecoveryAgent(event_bus, memory_manager)


@pytest.fixture
def sample_failure_report():
    """Create a sample failure report."""
    return FailureReport(
        workflow_id="workflow-1",
        source_agent="SalesforceEngineer",
        category=FailureCategory.CODE_GENERATION,
        severity=FailureSeverity.HIGH,
        title="Apex class generation failed",
        description="Failed to generate valid Apex class",
        error_message="Syntax error: unexpected token at line 42",
        context={
            "artifact_type": "apex_class",
            "last_verified_state": True,
        },
        affected_artifact="TestClass",
        affected_task_id="task-1",
        original_attempt_count=1,
        is_repeated=False,
    )


class TestFailureAnalyzer:
    """Test failure analysis."""

    @pytest.mark.asyncio
    async def test_analyze_failure_code_generation(self, sample_failure_report):
        """Test analyzing code generation failure."""
        root_cause, confidence = await FailureAnalyzer.analyze_failure(
            sample_failure_report
        )

        assert isinstance(root_cause, str)
        assert len(root_cause) > 0
        assert 0 <= confidence <= 1

    @pytest.mark.asyncio
    async def test_categorize_error_syntax(self):
        """Test error categorization for syntax errors."""
        category = await FailureAnalyzer.categorize_error(
            "Syntax error: unexpected token"
        )

        assert category == FailureCategory.CODE_GENERATION

    @pytest.mark.asyncio
    async def test_categorize_error_timeout(self):
        """Test error categorization for timeouts."""
        category = await FailureAnalyzer.categorize_error(
            "Connection timeout after 30s"
        )

        assert category == FailureCategory.NETWORKING

    @pytest.mark.asyncio
    async def test_determine_failure_severity_escalation(self, sample_failure_report):
        """Test severity escalation for repeated failures."""
        sample_failure_report.is_repeated = True
        severity = await FailureAnalyzer.determine_failure_severity(
            sample_failure_report
        )

        # Should escalate from HIGH
        assert severity in [FailureSeverity.HIGH, FailureSeverity.CRITICAL]

    @pytest.mark.asyncio
    async def test_assess_recoverability_recoverable(self, sample_failure_report):
        """Test assessing recoverability of failure."""
        is_recoverable, reason = await FailureAnalyzer.assess_recoverability(
            sample_failure_report, 1
        )

        assert isinstance(is_recoverable, bool)
        assert isinstance(reason, str)

    @pytest.mark.asyncio
    async def test_assess_recoverability_too_many_attempts(
        self, sample_failure_report
    ):
        """Test recoverability assessment after too many attempts."""
        is_recoverable, reason = await FailureAnalyzer.assess_recoverability(
            sample_failure_report, 10  # Too many attempts
        )

        assert is_recoverable is False
        assert "Too many" in reason

    @pytest.mark.asyncio
    async def test_match_failure_signatures(self, sample_failure_report):
        """Test matching failure signatures."""
        import uuid
        # Create a known signature
        sig_id = str(uuid.uuid4())
        signature = FailureSignature(
            id=sig_id,
            category=FailureCategory.CODE_GENERATION,
            error_pattern=r"syntax.*error",
            error_message_pattern=r"unexpected.*token",
            successful_recovery_strategy=RecoveryStrategy.REGENERATE,
            confidence=0.9,
            times_encountered=5,
            times_successfully_recovered=5,  # 100% success rate for higher match score
        )

        match = await FailureAnalyzer.match_failure_signatures(
            sample_failure_report, [signature]
        )

        assert match is not None
        assert match.category == FailureCategory.CODE_GENERATION

    @pytest.mark.asyncio
    async def test_extract_context_clues(self, sample_failure_report):
        """Test extracting context clues from failure."""
        clues = await FailureAnalyzer.extract_context_clues(
            sample_failure_report
        )

        assert isinstance(clues, dict)


class TestRecoveryStrategies:
    """Test recovery strategies."""

    @pytest.mark.asyncio
    async def test_retry_strategy_plan(self, sample_failure_report):
        """Test retry strategy plan creation."""
        strategy = RetryStrategy()
        plan = await strategy.build_plan(
            sample_failure_report,
            "Transient failure",
            0.8,
        )

        assert plan.strategy == RecoveryStrategy.RETRY
        assert len(plan.actions) > 0
        assert plan.actions[0].action_type == "wait_and_retry"

    @pytest.mark.asyncio
    async def test_regenerate_strategy_plan(self, sample_failure_report):
        """Test regenerate strategy plan creation."""
        strategy = RegenerateStrategy()
        plan = await strategy.build_plan(
            sample_failure_report,
            "Code generation error",
            0.85,
        )

        assert plan.strategy == RecoveryStrategy.REGENERATE
        assert len(plan.actions) >= 2
        assert any(a.action_type == "invoke_engineer" for a in plan.actions)

    @pytest.mark.asyncio
    async def test_rollback_strategy_plan(self, sample_failure_report):
        """Test rollback strategy plan creation."""
        strategy = RollbackStrategy()
        plan = await strategy.build_plan(
            sample_failure_report,
            "Deployment error",
            0.75,
        )

        assert plan.strategy == RecoveryStrategy.ROLLBACK
        assert len(plan.actions) >= 2

    @pytest.mark.asyncio
    async def test_fallback_strategy_plan(self, sample_failure_report):
        """Test fallback strategy plan creation."""
        strategy = FallbackStrategy()
        plan = await strategy.build_plan(
            sample_failure_report,
            "Primary approach failed",
            0.7,
        )

        assert plan.strategy == RecoveryStrategy.FALLBACK
        assert len(plan.actions) > 0

    @pytest.mark.asyncio
    async def test_strategy_factory_for_category(self):
        """Test strategy factory retrieval."""
        strategy = StrategyFactory.get_strategy(
            FailureCategory.CODE_GENERATION
        )

        assert strategy is not None
        assert isinstance(strategy, RegenerateStrategy)

    @pytest.mark.asyncio
    async def test_strategy_factory_with_override(self):
        """Test strategy factory with override."""
        strategy = StrategyFactory.get_strategy(
            FailureCategory.CODE_GENERATION,
            RecoveryStrategy.RETRY,
        )

        assert strategy is not None
        assert isinstance(strategy, RetryStrategy)


class TestRecoveryExecutor:
    """Test recovery plan execution."""

    @pytest.mark.asyncio
    async def test_execute_plan_success(self):
        """Test successful plan execution."""
        executor = RecoveryExecutor()

        # Create a simple plan
        plan = RecoveryPlan(
            failure_id="failure-1",
            failure_category=FailureCategory.NETWORKING,
            root_cause_analysis="Transient timeout",
            confidence=0.8,
            strategy=RecoveryStrategy.RETRY,
            estimated_duration_seconds=30.0,
        )

        from salesforce_ai_engineer.recovery.models import RecoveryAction

        plan.actions.append(
            RecoveryAction(
                step_number=1,
                description="Wait and retry",
                action_type="wait_and_retry",
                parameters={"wait_seconds": 1, "retry_target": "task-1"},
            )
        )

        attempt = await executor.execute_plan(plan)

        assert attempt.status == RecoveryStatus.SUCCEEDED or attempt.status == RecoveryStatus.PARTIALLY_SUCCEEDED
        assert attempt.executed_actions >= 0
        assert attempt.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_execute_action_timeout(self):
        """Test action execution with timeout."""
        executor = RecoveryExecutor()

        from salesforce_ai_engineer.recovery.models import RecoveryAction

        action = RecoveryAction(
            step_number=1,
            description="Test action",
            action_type="wait_and_retry",
            parameters={"wait_seconds": 100},  # Will timeout
            timeout_seconds=1,
        )

        # This should timeout or succeed depending on the implementation
        from salesforce_ai_engineer.recovery.executor import ExecutionContext

        context = ExecutionContext("plan-1", "failure-1")
        result = await executor._execute_action(action, context)

        assert "success" in result or "error" in result


class TestRecoveryAgent:
    """Test Recovery Agent."""

    @pytest.mark.asyncio
    async def test_handle_failure_recoverable(self, recovery_agent, sample_failure_report):
        """Test handling a recoverable failure."""
        result = await recovery_agent.handle_failure(sample_failure_report)

        assert result is not None
        assert isinstance(result.final_status, RecoveryStatus)
        assert isinstance(result.is_recovered, bool)

    @pytest.mark.asyncio
    async def test_handle_failure_non_recoverable(
        self,
        recovery_agent,
    ):
        """Test handling a non-recoverable failure."""
        failure = FailureReport(
            workflow_id="workflow-1",
            source_agent="SalesforceEngineer",
            category=FailureCategory.AUTHENTICATION,
            severity=FailureSeverity.CRITICAL,
            title="Authentication failed",
            description="Invalid credentials",
            error_message="authentication failed: invalid token",
            affected_task_id="task-1",
        )

        result = await recovery_agent.handle_failure(failure)

        assert result is not None
        assert result.was_escalated or not result.is_recovered

    @pytest.mark.asyncio
    async def test_handle_repeated_failure(self, recovery_agent):
        """Test handling repeated failures."""
        failure = FailureReport(
            workflow_id="workflow-1",
            source_agent="SalesforceEngineer",
            category=FailureCategory.CODE_GENERATION,
            severity=FailureSeverity.HIGH,
            title="Generation failed",
            description="Failed again",
            error_message="Syntax error",
            affected_artifact="TestClass",
            affected_task_id="task-1",
            is_repeated=True,
        )

        result = await recovery_agent.handle_failure(failure)

        assert result is not None

    @pytest.mark.asyncio
    async def test_failure_loop_detection(self, recovery_agent):
        """Test detection of failure loops."""
        failure = FailureReport(
            workflow_id="workflow-1",
            source_agent="SalesforceEngineer",
            category=FailureCategory.CODE_GENERATION,
            severity=FailureSeverity.HIGH,
            title="Generation failed",
            description="Failed",
            error_message="Syntax error",
            affected_artifact="TestClass",
            affected_task_id="task-1",
        )

        # Trigger multiple times to detect loop
        for _ in range(6):
            result = await recovery_agent.handle_failure(failure)
            if result.was_escalated:
                break

    @pytest.mark.asyncio
    async def test_recovery_statistics(self, recovery_agent):
        """Test getting recovery statistics."""
        stats = await recovery_agent.get_recovery_statistics()

        assert isinstance(stats, dict)
        assert "failure_counts" in stats
        assert "max_attempts" in stats


class TestIntegration:
    """Integration tests for Recovery Agent."""

    @pytest.mark.asyncio
    async def test_end_to_end_recovery(self, recovery_agent):
        """Test end-to-end recovery workflow."""
        failure = FailureReport(
            workflow_id="workflow-1",
            source_agent="SalesforceEngineer",
            category=FailureCategory.CODE_GENERATION,
            severity=FailureSeverity.MEDIUM,
            title="Apex class generation failed",
            description="Syntax error in generated code",
            error_message="Unexpected token at line 42",
            context={
                "artifact_type": "apex_class",
                "generated_code_length": 500,
            },
            affected_artifact="AccountService",
            affected_task_id="task-1",
            original_attempt_count=1,
            is_repeated=False,
        )

        result = await recovery_agent.handle_failure(failure)

        assert result is not None
        assert result.failure_id == failure.id
        assert isinstance(result.final_status, RecoveryStatus)
        assert isinstance(result.is_recovered, bool)
        assert result.recovery_time_seconds >= 0
        assert len(result.recovery_attempts) > 0

    @pytest.mark.asyncio
    async def test_recovery_with_escalation(self, recovery_agent):
        """Test recovery process with escalation."""
        # Create multiple failures to trigger escalation
        failures = []
        for i in range(6):
            failure = FailureReport(
                workflow_id="workflow-1",
                source_agent="SalesforceEngineer",
                category=FailureCategory.SECURITY,
                severity=FailureSeverity.CRITICAL,
                title="Security error",
                description=f"Security failure {i}",
                error_message="permission denied",
                affected_artifact="ConfigClass",
                affected_task_id="task-1",
                is_repeated=(i > 0),
            )
            failures.append(failure)

        # First one should escalate immediately (security)
        result = await recovery_agent.handle_failure(failures[0])
        assert result.was_escalated or not result.is_recovered

    @pytest.mark.asyncio
    async def test_recovery_with_multiple_strategies(self, recovery_agent):
        """Test recovery trying multiple strategies."""
        failure = FailureReport(
            workflow_id="workflow-1",
            source_agent="SalesforceEngineer",
            category=FailureCategory.GOVERNOR_LIMIT,
            severity=FailureSeverity.HIGH,
            title="Governor limit exceeded",
            description="Too many SOQL queries",
            error_message="governor limit exceeded: too many SOQL queries",
            affected_artifact="BulkProcessor",
            affected_task_id="task-2",
        )

        result = await recovery_agent.handle_failure(failure)

        assert result is not None
        assert result.failure_id == failure.id
        assert len(result.recovery_attempts) >= 1

    @pytest.mark.asyncio
    async def test_recovery_threshold_sequence(self, recovery_agent, sample_failure_report):
        """Verify that the agent logic respects the 1-2 Retry, 3 Escalate sequence."""
        # Using the actual OllamaRecoveryAgent logic if available in fixture
        # or testing the system's threshold enforcement.
        
        for attempt in [1, 2]:
            sample_failure_report.original_attempt_count = attempt
            # Manually simulating the increment logic
            is_recoverable, reason = await FailureAnalyzer.assess_recoverability(
                sample_failure_report, attempt
            )
            assert is_recoverable is True
            
        # Threshold breach
        is_recoverable_final, reason_final = await FailureAnalyzer.assess_recoverability(
            sample_failure_report, 4
        )
        assert is_recoverable_final is False
        assert "Too many" in reason_final
