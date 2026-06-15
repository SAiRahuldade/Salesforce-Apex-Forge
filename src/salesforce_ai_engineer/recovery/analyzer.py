"""Failure analysis and root cause detection."""

import re
import logging
from typing import Optional, Tuple

from salesforce_ai_engineer.recovery.models import (
    FailureReport,
    FailureCategory,
    FailureSeverity,
    FailureSignature,
)

logger = logging.getLogger(__name__)


class FailureAnalyzer:
    """Analyzes failures to determine root causes and recovery strategies."""

    # Error pattern mappings for failure classification
    PATTERN_MAPPINGS = {
        FailureCategory.CODE_GENERATION: [
            r"generation failed",
            r"syntax error",
            r"compilation error",
            r"invalid.*syntax",
        ],
        FailureCategory.METADATA: [
            r"metadata.*invalid",
            r"invalid.*metadata",
            r"field.*not found",
            r"object.*not found",
            r"field_integrity_exception",
            r"duplicate_developer_name",
        ],
        FailureCategory.DEPLOYMENT: [
            r"deployment.*failed",
            r"deploy.*error",
            r"push.*failed",
            r"cannot.*deploy",
        ],
        FailureCategory.AUTHENTICATION: [
            r"authentication.*failed",
            r"unauthorized",
            r"invalid.*token",
            r"credentials.*invalid",
            r"invalid_session_id",
            r"oauth_app_access_denied",
            r"expired_session",
        ],
        FailureCategory.NETWORKING: [
            r"connection.*failed",
            r"timeout",
            r"network.*error",
            r"host.*unreachable",
        ],
        FailureCategory.DEPENDENCY: [
            r"dependency.*not found",
            r"missing.*dependency",
            r"cannot.*find.*module",
            r"import.*error",
        ],
        FailureCategory.VALIDATION: [
            r"validation.*failed",
            r"invalid.*value",
            r"constraint.*violated",
            r"field_custom_validation_exception",
            r"duplicate_value",
            r"required_field_missing",
            r"validation.*error",
        ],
        FailureCategory.GOVERNOR_LIMIT: [
            r"governor.*limit",
            r"limit.*exceeded",
            r"too many.*queries",
            r"dml.*limit",
            r"query_timeout",
            r"request_limit_exceeded",
        ],
        FailureCategory.SECURITY: [
            r"security.*error",
            r"permission.*denied",
            r"access.*denied",
            r"forbidden",
        ],
        FailureCategory.RUNTIME: [
            r"runtime.*error",
            r"exception",
            r"error.*occurred",
            r"fatal.*error",
        ],
        FailureCategory.FILESYSTEM: [
            r"file.*not found",
            r"permission.*denied",
            r"cannot.*write",
            r"path.*invalid",
        ],
        FailureCategory.CONFIGURATION: [
            r"configuration.*error",
            r"config.*invalid",
            r"missing.*config",
            r"invalid.*setting",
        ],
    }

    @staticmethod
    async def analyze_failure(failure_report: FailureReport) -> Tuple[str, float]:
        """Analyze a failure and determine root cause.

        Args:
            failure_report: FailureReport to analyze

        Returns:
            Tuple of (root_cause_analysis, confidence_score)
        """
        analysis_parts = []
        confidence = 0.7  # Start with baseline confidence

        # Analyze error message patterns
        error_lower = failure_report.error_message.lower()
        message_matches = []

        for pattern in [
            r"null.*reference",
            r"attribute.*error",
            r"undefined.*method",
            r"cannot.*access",
        ]:
            if re.search(pattern, error_lower):
                message_matches.append("Null reference or missing attribute")

        for pattern in [r"syntax.*error", r"unexpected.*token", r"invalid.*syntax"]:
            if re.search(pattern, error_lower):
                message_matches.append("Syntax error in generated code")
                confidence = 0.85

        for pattern in [r"timeout", r"connection.*refused"]:
            if re.search(pattern, error_lower):
                message_matches.append("Network or connection timeout")

        if message_matches:
            analysis_parts.extend(message_matches)

        # Analyze context
        if failure_report.context:
            if "last_verified_state" in failure_report.context:
                analysis_parts.append(
                    "Failure occurred after verification step completed"
                )
                confidence += 0.1

            if "rollback_required" in failure_report.context:
                analysis_parts.append("Previous changes may need rollback")
                confidence += 0.1

            if "external_service" in failure_report.context:
                analysis_parts.append(
                    "Failure may involve external service dependency"
                )
                confidence -= 0.1

        # Analyze affected artifact
        if failure_report.affected_artifact:
            analysis_parts.append(
                f"Affected artifact: {failure_report.affected_artifact}"
            )

        # Analyze repetition
        if failure_report.is_repeated:
            analysis_parts.append(
                "Failure is repeated - may indicate systematic issue"
            )
            confidence -= 0.15

        root_cause = ". ".join(analysis_parts) or "Unknown root cause"
        confidence = max(0.0, min(1.0, confidence))  # Clamp to 0-1

        logger.debug(
            f"Failure analysis complete: confidence={confidence}, cause={root_cause}"
        )

        return root_cause, confidence

    @staticmethod
    async def match_failure_signatures(
        failure_report: FailureReport,
        known_signatures: list[FailureSignature],
    ) -> Optional[FailureSignature]:
        """Find matching failure signature from history.

        Args:
            failure_report: Current failure report
            known_signatures: List of known failure signatures

        Returns:
            Matching FailureSignature or None
        """
        best_match = None
        best_score = 0.0

        error_lower = failure_report.error_message.lower()
        description_lower = failure_report.description.lower()

        for sig in known_signatures:
            if sig.category != failure_report.category:
                continue

            score = 0.0

            # Check error pattern match
            if re.search(sig.error_pattern, error_lower):
                score += 0.4

            # Check error message pattern
            if re.search(sig.error_message_pattern, error_lower):
                score += 0.3

            # Check context patterns
            context_matches = 0
            for key, pattern in sig.context_patterns.items():
                if key in failure_report.context:
                    if re.search(
                        pattern, str(failure_report.context[key]).lower()
                    ):
                        context_matches += 1

            if sig.context_patterns:
                context_score = context_matches / len(sig.context_patterns)
                score += context_score * 0.3

            # Weight by known success rate
            score *= sig.success_rate

            if score > best_score:
                best_score = score
                best_match = sig

        if best_match and best_score >= 0.6:
            logger.info(
                f"Found matching signature with score {best_score}: {best_match.id}"
            )
            return best_match

        return None

    @staticmethod
    async def determine_failure_severity(failure_report: FailureReport) -> FailureSeverity:
        """Determine severity of a failure based on context.

        Args:
            failure_report: FailureReport to analyze

        Returns:
            FailureSeverity level
        """
        # Start with provided severity
        severity = failure_report.severity

        # Escalate if repeated
        if failure_report.is_repeated:
            if severity == FailureSeverity.LOW:
                severity = FailureSeverity.MEDIUM
            elif severity == FailureSeverity.MEDIUM:
                severity = FailureSeverity.HIGH
            elif severity == FailureSeverity.HIGH:
                severity = FailureSeverity.CRITICAL

        # Escalate if security related
        if failure_report.category == FailureCategory.SECURITY:
            if severity in [FailureSeverity.LOW, FailureSeverity.MEDIUM]:
                severity = FailureSeverity.HIGH

        # Escalate if governor limits
        if failure_report.category == FailureCategory.GOVERNOR_LIMIT:
            if severity in [FailureSeverity.LOW, FailureSeverity.MEDIUM]:
                severity = FailureSeverity.HIGH

        return severity

    @staticmethod
    async def assess_recoverability(
        failure_report: FailureReport,
        attempt_count: int,
    ) -> Tuple[bool, str]:
        """Assess whether a failure is likely recoverable.

        Args:
            failure_report: FailureReport to assess
            attempt_count: Number of recovery attempts already made

        Returns:
            Tuple of (is_recoverable, reason)
        """
        # Hard failures that are not recoverable
        unrecoverable_categories = [
            FailureCategory.AUTHENTICATION,
            FailureCategory.CONFIGURATION,
        ]

        if failure_report.category in unrecoverable_categories:
            return False, f"{failure_report.category} failures require manual intervention"

        # Too many attempts (threshold: 3)
        if attempt_count >= 3:
            return (
                False,
                f"Too many recovery attempts ({attempt_count}). Likely unrecoverable.",
            )

        # Security breaches
        if failure_report.category == FailureCategory.SECURITY:
            return False, "Security failures require manual review"

        # Default: likely recoverable
        return True, "Failure appears recoverable"

    @staticmethod
    async def categorize_error(error_message: str) -> FailureCategory:
        """Categorize an error by matching patterns.

        Args:
            error_message: Error message to categorize

        Returns:
            FailureCategory
        """
        error_lower = error_message.lower()

        for category, patterns in FailureAnalyzer.PATTERN_MAPPINGS.items():
            for pattern in patterns:
                if re.search(pattern, error_lower):
                    return category

        # Default to system error
        return FailureCategory.SYSTEM

    @staticmethod
    async def extract_context_clues(
        failure_report: FailureReport,
    ) -> dict[str, str]:
        """Extract useful context clues from failure for debugging.

        Args:
            failure_report: FailureReport to analyze

        Returns:
            Dictionary of extracted context clues
        """
        clues = {}

        error_lower = failure_report.error_message.lower()

        # Extract file paths
        file_paths = re.findall(r"['\"]([a-zA-Z0-9/_.-]+\.[a-z]+)['\"]", error_lower)
        if file_paths:
            clues["files_involved"] = ", ".join(set(file_paths[:5]))

        # Extract method names
        methods = re.findall(r"\.([a-zA-Z_]\w+)\(", error_lower)
        if methods:
            clues["methods_involved"] = ", ".join(set(methods[:5]))

        # Extract line numbers
        lines = re.findall(r"line\s+(\d+)", error_lower)
        if lines:
            clues["error_lines"] = ", ".join(lines[:5])

        # Extract object/class names
        objects = re.findall(r"([A-Z][a-zA-Z0-9]+)\s+(class|object)", error_lower)
        if objects:
            clues["classes_involved"] = ", ".join([obj[0] for obj in objects[:5]])

        return clues
