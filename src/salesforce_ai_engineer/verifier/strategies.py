"""Verification strategies for different Salesforce artifact types."""

import logging
from typing import Any

from salesforce_ai_engineer.verifier.models import (
    VerificationIssue,
    ArtifactType,
    IssueSeverity,
    IssueCategory,
)
from salesforce_ai_engineer.verifier.analyzer import StaticAnalyzer

logger = logging.getLogger(__name__)


class VerificationStrategy:
    """Base verification strategy."""

    async def verify(self, artifact_id: str, artifact_content: Any) -> list[VerificationIssue]:
        """Verify an artifact and return issues found."""
        raise NotImplementedError


class ApexVerificationStrategy(VerificationStrategy):
    """Verification strategy for Apex code."""

    async def verify(self, artifact_id: str, code: str) -> list[VerificationIssue]:
        """Verify Apex code."""
        issues = []

        # Syntax analysis
        issues.extend(await StaticAnalyzer.analyze_apex_syntax(code, artifact_id))

        # Security analysis
        issues.extend(await StaticAnalyzer.analyze_soql_injection_risk(code, artifact_id))
        issues.extend(await StaticAnalyzer.analyze_crud_fls_compliance(code, artifact_id))

        # Governor limit analysis
        issues.extend(await StaticAnalyzer.analyze_dml_in_loop(code, artifact_id))

        # Performance analysis
        issues.extend(await StaticAnalyzer.analyze_performance(code, artifact_id))

        # Naming conventions
        issues.extend(await StaticAnalyzer.analyze_naming_conventions(code, ArtifactType.APEX_CLASS))

        # Check for try-catch with broad exception
        if "catch (Exception e)" in code:
            issues.append(
                VerificationIssue(
                    artifact_id=artifact_id,
                    artifact_type=ArtifactType.APEX_CLASS,
                    category=IssueCategory.BEST_PRACTICE,
                    severity=IssueSeverity.MEDIUM,
                    title="Broad exception catch",
                    description="Code catches broad Exception class instead of specific exceptions",
                    root_cause="Catching Exception masks real errors",
                    confidence=0.85,
                    recommendations=["Catch specific exception types instead of Exception"],
                    affected_components=[artifact_id],
                    remediation_effort="low",
                )
            )

        # Check for missing annotations
        if "Transient" not in code and "public static Map<" in code:
            issues.append(
                VerificationIssue(
                    artifact_id=artifact_id,
                    artifact_type=ArtifactType.APEX_CLASS,
                    category=IssueCategory.BEST_PRACTICE,
                    severity=IssueSeverity.LOW,
                    title="Consider using @Transient annotation",
                    description="Large collections should use @Transient for serialization",
                    root_cause="Unserializable objects impact performance",
                    confidence=0.70,
                    recommendations=["Mark transient data with @Transient annotation"],
                    remediation_effort="low",
                )
            )

        return issues


class TriggerVerificationStrategy(VerificationStrategy):
    """Verification strategy for Apex Triggers."""

    async def verify(self, artifact_id: str, code: str) -> list[VerificationIssue]:
        """Verify Apex trigger."""
        issues = []

        # Verify trigger structure
        if "trigger " not in code:
            issues.append(
                VerificationIssue(
                    artifact_id=artifact_id,
                    artifact_type=ArtifactType.APEX_TRIGGER,
                    category=IssueCategory.SYNTAX_ERROR,
                    severity=IssueSeverity.CRITICAL,
                    title="Invalid trigger syntax",
                    description="Code does not contain trigger declaration",
                    root_cause="File must contain trigger keyword",
                    confidence=0.95,
                    recommendations=["Ensure file is a valid Apex trigger"],
                    remediation_effort="medium",
                )
            )

        # Check for trigger events
        events = ["before insert", "after insert", "before update", "after update", "before delete", "after delete"]
        has_event = any(event in code.lower() for event in events)

        if not has_event:
            issues.append(
                VerificationIssue(
                    artifact_id=artifact_id,
                    artifact_type=ArtifactType.APEX_TRIGGER,
                    category=IssueCategory.SYNTAX_ERROR,
                    severity=IssueSeverity.CRITICAL,
                    title="No trigger events specified",
                    description="Trigger must specify at least one event",
                    root_cause="Trigger requires 'before insert', 'after insert', etc.",
                    confidence=0.95,
                    recommendations=["Add trigger events"],
                    remediation_effort="low",
                )
            )

        # Security analysis
        issues.extend(await StaticAnalyzer.analyze_soql_injection_risk(code, artifact_id))
        issues.extend(await StaticAnalyzer.analyze_dml_in_loop(code, artifact_id))

        return issues


class LWCVerificationStrategy(VerificationStrategy):
    """Verification strategy for Lightning Web Components."""

    async def verify(self, artifact_id: str, files: dict[str, str]) -> list[VerificationIssue]:
        """Verify LWC component files."""
        issues = []

        # Verify file structure
        issues.extend(await StaticAnalyzer.analyze_lwc_structure(files))

        # Verify JavaScript
        if "js" in str(files):
            js_code = next((v for k, v in files.items() if k.endswith(".js")), "")
            if js_code:
                # Check for proper lifecycle hooks
                if "connectedCallback" not in js_code and "renderedCallback" not in js_code:
                    issues.append(
                        VerificationIssue(
                            artifact_id=artifact_id,
                            artifact_type=ArtifactType.LWC,
                            category=IssueCategory.BEST_PRACTICE,
                            severity=IssueSeverity.LOW,
                            title="No lifecycle hooks",
                            description="Component missing standard lifecycle hooks",
                            root_cause="LWCs should implement lifecycle hooks",
                            confidence=0.70,
                            recommendations=["Add connectedCallback or renderedCallback"],
                            remediation_effort="low",
                        )
                    )

        # Verify HTML template
        if "html" in str(files):
            html_content = next((v for k, v in files.items() if k.endswith(".html")), "")
            if html_content:
                if "<template>" not in html_content:
                    issues.append(
                        VerificationIssue(
                            artifact_id=artifact_id,
                            artifact_type=ArtifactType.LWC,
                            category=IssueCategory.SYNTAX_ERROR,
                            severity=IssueSeverity.CRITICAL,
                            title="Missing template tag",
                            description="LWC HTML must be wrapped in <template>",
                            root_cause="LWC HTML templates require <template> root element",
                            confidence=0.95,
                            recommendations=["Wrap HTML content in <template> tags"],
                            remediation_effort="low",
                        )
                    )

        return issues


class FlowVerificationStrategy(VerificationStrategy):
    """Verification strategy for Flows."""

    async def verify(self, artifact_id: str, flow_xml: str) -> list[VerificationIssue]:
        """Verify Flow definition."""
        issues = []

        # Verify XML structure
        if "<?xml" not in flow_xml or "<Flow" not in flow_xml:
            issues.append(
                VerificationIssue(
                    artifact_id=artifact_id,
                    artifact_type=ArtifactType.FLOW,
                    category=IssueCategory.SYNTAX_ERROR,
                    severity=IssueSeverity.CRITICAL,
                    title="Invalid Flow XML",
                    description="Flow XML missing required structure",
                    root_cause="Flow must be valid XML with Flow root element",
                    confidence=0.95,
                    recommendations=["Validate Flow XML structure"],
                    remediation_effort="medium",
                )
            )

        # Verify Flow name
        if "<name>" not in flow_xml or "<name></name>" in flow_xml:
            issues.append(
                VerificationIssue(
                    artifact_id=artifact_id,
                    artifact_type=ArtifactType.FLOW,
                    category=IssueCategory.METADATA_CONSISTENCY,
                    severity=IssueSeverity.HIGH,
                    title="Missing or empty Flow name",
                    description="Flow must have a name",
                    root_cause="Flow name is required metadata",
                    confidence=0.95,
                    recommendations=["Add unique Flow name"],
                    remediation_effort="low",
                )
            )

        # Analyze logic
        issues.extend(await StaticAnalyzer.analyze_flow_logic(flow_xml, artifact_id))

        return issues


class MetadataVerificationStrategy(VerificationStrategy):
    """Verification strategy for metadata definitions."""

    async def verify(self, artifact_id: str, metadata: dict[str, Any]) -> list[VerificationIssue]:
        """Verify metadata object."""
        issues = []

        # Consistency analysis
        issues.extend(await StaticAnalyzer.analyze_metadata_consistency(metadata, artifact_id))

        # Type-specific validation
        metadata_type = metadata.get("type", "")

        if metadata_type == "CustomObject":
            # Validate custom object
            if "fields" in metadata and not metadata.get("label"):
                issues.append(
                    VerificationIssue(
                        artifact_id=artifact_id,
                        artifact_type=ArtifactType.CUSTOM_OBJECT,
                        category=IssueCategory.METADATA_CONSISTENCY,
                        severity=IssueSeverity.MEDIUM,
                        title="Missing object label",
                        description="Custom object should have a label",
                        root_cause="Labels improve user experience",
                        confidence=0.85,
                        recommendations=["Add descriptive label"],
                        remediation_effort="low",
                    )
                )

        elif metadata_type == "ValidationRule":
            if "formula" not in metadata:
                issues.append(
                    VerificationIssue(
                        artifact_id=artifact_id,
                        artifact_type=ArtifactType.VALIDATION_RULE,
                        category=IssueCategory.SYNTAX_ERROR,
                        severity=IssueSeverity.CRITICAL,
                        title="Validation rule missing formula",
                        description="ValidationRule requires formula field",
                        root_cause="Formula is required metadata",
                        confidence=0.95,
                        recommendations=["Add validation formula"],
                        remediation_effort="low",
                    )
                )

        return issues


class SOQLVerificationStrategy(VerificationStrategy):
    """Verification strategy for SOQL queries."""

    async def verify(self, artifact_id: str, soql: str) -> list[VerificationIssue]:
        """Verify SOQL query."""
        issues = []

        # Check for SELECT *
        if "SELECT *" in soql or "select *" in soql:
            issues.append(
                VerificationIssue(
                    artifact_id=artifact_id,
                    artifact_type=ArtifactType.SOQL,
                    category=IssueCategory.PERFORMANCE,
                    severity=IssueSeverity.HIGH,
                    title="SOQL uses SELECT *",
                    description="SELECT * retrieves unnecessary fields",
                    root_cause="Explicit field selection improves performance",
                    confidence=0.95,
                    recommendations=["Specify required fields explicitly"],
                    remediation_effort="low",
                )
            )

        # Check for LIMIT
        if "LIMIT" not in soql and "limit" not in soql:
            issues.append(
                VerificationIssue(
                    artifact_id=artifact_id,
                    artifact_type=ArtifactType.SOQL,
                    category=IssueCategory.BEST_PRACTICE,
                    severity=IssueSeverity.MEDIUM,
                    title="SOQL missing LIMIT clause",
                    description="SOQL query should specify LIMIT",
                    root_cause="LIMIT prevents unexpected large result sets",
                    confidence=0.80,
                    recommendations=["Add LIMIT clause to query"],
                    remediation_effort="low",
                )
            )

        return issues


class StrategyFactory:
    """Factory for creating verification strategies."""

    _strategies = {
        ArtifactType.APEX_CLASS: ApexVerificationStrategy,
        ArtifactType.APEX_TRIGGER: TriggerVerificationStrategy,
        ArtifactType.BATCH_APEX: ApexVerificationStrategy,
        ArtifactType.QUEUEABLE_APEX: ApexVerificationStrategy,
        ArtifactType.SCHEDULED_APEX: ApexVerificationStrategy,
        ArtifactType.LWC: LWCVerificationStrategy,
        ArtifactType.FLOW: FlowVerificationStrategy,
        ArtifactType.VALIDATION_RULE: MetadataVerificationStrategy,
        ArtifactType.PERMISSION_SET: MetadataVerificationStrategy,
        ArtifactType.CUSTOM_OBJECT: MetadataVerificationStrategy,
        ArtifactType.SOQL: SOQLVerificationStrategy,
    }

    @staticmethod
    def get_strategy(artifact_type: ArtifactType) -> VerificationStrategy:
        """Get verification strategy for artifact type."""
        strategy_class = StrategyFactory._strategies.get(artifact_type, ApexVerificationStrategy)
        return strategy_class()

    @staticmethod
    def register_strategy(artifact_type: ArtifactType, strategy_class: type):
        """Register a custom verification strategy."""
        StrategyFactory._strategies[artifact_type] = strategy_class
