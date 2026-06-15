"""Verifier Agent - independently verifies and validates Salesforce artifacts."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any
import uuid

from salesforce_ai_engineer.agent.models import ExecutionPlan, ExecutionTask, SalesforceWorkType
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.verifier.models import (
    VerificationReport,
    VerificationIssue,
    QualityScore,
    ArtifactType,
    IssueSeverity,
)
from salesforce_ai_engineer.verifier.analyzer import StaticAnalyzer
from salesforce_ai_engineer.verifier.scorer import QualityScorer
from salesforce_ai_engineer.verifier.strategies import StrategyFactory

UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)


class VerifierError(Exception):
    """Base exception for Verifier Agent."""
    pass


class VerifierAgent:
    """Agent that verifies and validates Salesforce artifacts."""

    def __init__(self, event_bus: EventBus, memory_manager: MemoryManager):
        """Initialize Verifier Agent.

        Args:
            event_bus: EventBus for publishing verification events
            memory_manager: MemoryManager for persisting results
        """
        self.event_bus = event_bus
        self.memory_manager = memory_manager
        self.logger = logger

    async def verify_plan(
        self,
        plan: ExecutionPlan,
        artifacts: dict[str, Any],
        workflow_id: str,
    ) -> VerificationReport:
        """Verify all artifacts from an execution plan.

        Args:
            plan: Execution plan that was implemented
            artifacts: Dictionary of generated artifacts
            workflow_id: Workflow identifier for tracking

        Returns:
            VerificationReport with detailed findings
        """
        try:
            verification_id = str(uuid.uuid4())
            start_time = datetime.now(UTC)

            self.logger.info(
                f"Starting verification for workflow {workflow_id}, plan {plan.id}"
            )

            # Emit verification started event
            await self.event_bus.publish(
                "verifier.verification_started",
                {
                    "workflow_id": workflow_id,
                    "plan_id": plan.id,
                    "verification_id": verification_id,
                    "artifacts_count": len(artifacts),
                },
            )

            # Verify each artifact
            all_issues = []
            component_metrics = []

            for artifact_id, artifact_content in artifacts.items():
                self.logger.debug(f"Verifying artifact {artifact_id}")

                # Determine artifact type from metadata or content
                artifact_type = self._infer_artifact_type(artifact_id, artifact_content)

                # Get verification strategy
                strategy = StrategyFactory.get_strategy(artifact_type)

                # Verify artifact
                issues = await strategy.verify(artifact_id, artifact_content)
                all_issues.extend(issues)

                # Calculate component metrics
                code_content = (
                    artifact_content
                    if isinstance(artifact_content, str)
                    else str(artifact_content)
                )
                metrics = await QualityScorer.calculate_component_metrics(
                    artifact_id,
                    artifact_type.value,
                    code_content,
                    issues,
                )
                component_metrics.append(metrics)

            # Calculate overall quality score
            quality_score = await QualityScorer.calculate_overall_quality_score(
                plan.id, component_metrics
            )

            # Determine deployment approval
            critical_count = sum(1 for i in all_issues if i.severity == IssueSeverity.CRITICAL)
            high_count = sum(1 for i in all_issues if i.severity == IssueSeverity.HIGH)

            approved, approval_reason = await QualityScorer.determine_deployment_approval(
                quality_score, critical_count, high_count
            )

            # Generate recovery recommendations if needed
            recovery_recommendations = []
            if not approved:
                recovery_recommendations = self._generate_recovery_recommendations(all_issues)

            # Count issues by severity
            info_count = sum(1 for i in all_issues if i.severity == IssueSeverity.INFO)
            low_count = sum(1 for i in all_issues if i.severity == IssueSeverity.LOW)
            medium_count = sum(1 for i in all_issues if i.severity == IssueSeverity.MEDIUM)

            # Create verification report
            report = VerificationReport(
                workflow_id=workflow_id,
                plan_id=plan.id,
                artifacts_analyzed=len(artifacts),
                total_issues=len(all_issues),
                critical_issues=critical_count,
                high_issues=high_count,
                medium_issues=medium_count,
                low_issues=low_count,
                info_issues=info_count,
                issues=all_issues,
                quality_score=quality_score,
                approved_for_deployment=approved,
                approval_notes=approval_reason if approved else "",
                rejection_reason=approval_reason if not approved else "",
                recovery_recommendations=recovery_recommendations,
                verification_duration_seconds=(
                    datetime.now(UTC) - start_time
                ).total_seconds(),
            )

            # Store verification report in memory
            await self.memory_manager.store_project_memory(
                title=f"Verification Report: {plan.project or plan.id}",
                key_insights=[
                    f"Total issues found: {len(all_issues)}",
                    f"Critical issues: {critical_count}",
                    f"Quality score: {quality_score.overall_score}",
                    f"Approved for deployment: {approved}",
                ],
                technical_stack=["VerifierAgent", "StaticAnalysis", "QualityScoring"],
                created_by="verifier",
            )

            # Emit verification completed event
            await self.event_bus.publish(
                "verifier.verification_completed",
                {
                    "workflow_id": workflow_id,
                    "plan_id": plan.id,
                    "report_id": report.id,
                    "approved": approved,
                    "quality_score": quality_score.overall_score,
                    "issues_count": len(all_issues),
                },
            )

            self.logger.info(
                f"Verification completed: approved={approved}, "
                f"quality_score={quality_score.overall_score}, "
                f"issues={len(all_issues)}"
            )

            return report

        except Exception as e:
            self.logger.error(f"Verification failed: {e}", exc_info=True)
            await self.event_bus.publish(
                "verifier.verification_failed",
                {
                    "workflow_id": workflow_id,
                    "error": str(e),
                },
            )
            raise VerifierError(f"Verification failed: {e}") from e

    async def verify_artifact(
        self,
        artifact_id: str,
        artifact_content: Any,
        artifact_type: ArtifactType,
    ) -> list[VerificationIssue]:
        """Verify a single artifact.

        Args:
            artifact_id: Unique artifact identifier
            artifact_content: Content of the artifact
            artifact_type: Type of artifact

        Returns:
            List of verification issues found
        """
        strategy = StrategyFactory.get_strategy(artifact_type)
        return await strategy.verify(artifact_id, artifact_content)

    def _infer_artifact_type(self, artifact_id: str, content: Any) -> ArtifactType:
        """Infer artifact type from ID and content."""
        artifact_id_lower = artifact_id.lower()

        # Pattern matching
        if "trigger" in artifact_id_lower:
            return ArtifactType.APEX_TRIGGER
        elif "batch" in artifact_id_lower or "batchable" in str(content).lower():
            return ArtifactType.BATCH_APEX
        elif "queueable" in artifact_id_lower or "Queueable" in str(content):
            return ArtifactType.QUEUEABLE_APEX
        elif "scheduled" in artifact_id_lower or "Schedulable" in str(content):
            return ArtifactType.SCHEDULED_APEX
        elif "flow" in artifact_id_lower or ".flow" in artifact_id_lower:
            return ArtifactType.FLOW
        elif ("lwc" in artifact_id_lower or 
              isinstance(content, dict) and any(k.endswith('.js') for k in content.keys())):
            return ArtifactType.LWC
        elif "soql" in artifact_id_lower:
            return ArtifactType.SOQL
        elif "sosl" in artifact_id_lower:
            return ArtifactType.SOSL
        elif "validation" in artifact_id_lower or "ValidationRule" in str(content):
            return ArtifactType.VALIDATION_RULE
        elif "permission" in artifact_id_lower or "PermissionSet" in str(content):
            return ArtifactType.PERMISSION_SET
        elif "profile" in artifact_id_lower or "Profile" in str(content):
            return ArtifactType.PROFILE
        elif "sharing" in artifact_id_lower or "SharingRule" in str(content):
            return ArtifactType.SHARING_RULE
        elif "object" in artifact_id_lower or "CustomObject" in str(content):
            return ArtifactType.CUSTOM_OBJECT
        elif "field" in artifact_id_lower or "CustomField" in str(content):
            return ArtifactType.CUSTOM_FIELD
        else:
            # Default to Apex class
            return ArtifactType.APEX_CLASS

    def _generate_recovery_recommendations(self, issues: list[VerificationIssue]) -> list[str]:
        """Generate recovery recommendations based on issues found."""
        recommendations = []

        # Group issues by severity and category
        critical_issues = [i for i in issues if i.severity == IssueSeverity.CRITICAL]
        high_issues = [i for i in issues if i.severity == IssueSeverity.HIGH]

        if critical_issues:
            recommendations.append(
                f"Address all {len(critical_issues)} critical issues before deployment: "
                f"{', '.join(set(i.category.value for i in critical_issues))}"
            )

        if high_issues:
            recommendations.append(
                f"Resolve {len(high_issues)} high-severity issues: "
                f"{', '.join(set(i.category.value for i in high_issues))}"
            )

        # Add specific recommendations
        security_issues = [i for i in critical_issues + high_issues 
                          if i.category == "security" or i.category == "crud_fls"]
        if security_issues:
            recommendations.append("Priority: Fix all security vulnerabilities before retry")

        governor_issues = [i for i in critical_issues + high_issues 
                          if i.category == "governor_limit"]
        if governor_issues:
            recommendations.append(
                "Optimize code to comply with Salesforce governor limits"
            )

        # Send to Recovery Agent for specialized handling
        recommendations.append(
            "Send to Recovery Agent for specialized issue resolution and revalidation"
        )

        return recommendations

    async def compare_artifacts(
        self,
        old_artifact: Any,
        new_artifact: Any,
        artifact_type: ArtifactType,
    ) -> dict[str, Any]:
        """Compare old and new versions of an artifact.

        Args:
            old_artifact: Previous version
            new_artifact: New version
            artifact_type: Type of artifact

        Returns:
            Comparison report with changes and risk assessment
        """
        old_str = old_artifact if isinstance(old_artifact, str) else str(old_artifact)
        new_str = new_artifact if isinstance(new_artifact, str) else str(new_artifact)

        # Simple diff
        old_lines = set(old_str.split("\n"))
        new_lines = set(new_str.split("\n"))

        added_lines = new_lines - old_lines
        removed_lines = old_lines - new_lines

        # Risk assessment
        risk_level = "low"
        if artifact_type == ArtifactType.APEX_TRIGGER:
            risk_level = "high"  # Triggers are high risk
        elif artifact_type in [ArtifactType.VALIDATION_RULE, ArtifactType.SHARING_RULE]:
            risk_level = "medium"

        return {
            "lines_added": len(added_lines),
            "lines_removed": len(removed_lines),
            "added_lines": list(added_lines)[:10],  # First 10
            "removed_lines": list(removed_lines)[:10],
            "risk_level": risk_level,
            "requires_testing": True,
        }
