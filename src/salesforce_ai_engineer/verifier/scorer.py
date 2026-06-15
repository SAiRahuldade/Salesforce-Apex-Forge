"""Quality scoring module for Verifier Agent."""

import logging
from typing import Any

from salesforce_ai_engineer.verifier.models import (
    VerificationIssue,
    ComponentMetrics,
    QualityScore,
    IssueSeverity,
)

logger = logging.getLogger(__name__)


class QualityScorer:
    """Calculates quality scores for Salesforce artifacts."""

    SEVERITY_WEIGHTS = {
        IssueSeverity.CRITICAL: 100,
        IssueSeverity.HIGH: 50,
        IssueSeverity.MEDIUM: 25,
        IssueSeverity.LOW: 10,
        IssueSeverity.INFO: 1,
    }

    @staticmethod
    async def calculate_component_metrics(
        component_id: str,
        artifact_type: str,
        code: str,
        issues: list[VerificationIssue],
    ) -> ComponentMetrics:
        """Calculate metrics for a single component."""
        lines = code.split("\n")
        total_lines = len([line for line in lines if line.strip()])

        # Count issues by severity
        critical_count = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)
        high_count = sum(1 for i in issues if i.severity == IssueSeverity.HIGH)
        medium_count = sum(1 for i in issues if i.severity == IssueSeverity.MEDIUM)
        low_count = sum(1 for i in issues if i.severity == IssueSeverity.LOW)
        info_count = sum(1 for i in issues if i.severity == IssueSeverity.INFO)

        # Calculate complexity (simplified)
        complexity_score = await QualityScorer._calculate_complexity(code)

        # Calculate security score
        security_score = await QualityScorer._calculate_security_score(issues)

        # Calculate performance score
        performance_score = await QualityScorer._calculate_performance_score(issues, code)

        # Calculate maintainability score
        maintainability_score = await QualityScorer._calculate_maintainability_score(
            issues, total_lines, complexity_score
        )

        return ComponentMetrics(
            component_id=component_id,
            component_type=artifact_type,
            total_lines=total_lines,
            complexity_score=complexity_score,
            security_score=security_score,
            performance_score=performance_score,
            maintainability_score=maintainability_score,
            coverage_score=0.0,  # Would be filled from test coverage data
            issue_count=len(issues),
            critical_issues=critical_count,
            high_issues=high_count,
            medium_issues=medium_count,
            low_issues=low_count,
            info_issues=info_count,
        )

    @staticmethod
    async def _calculate_complexity(code: str) -> float:
        """Calculate cyclomatic complexity (0-10 scale)."""
        # Simplified calculation based on control flow statements
        control_flow_keywords = ["if", "else", "for", "while", "switch", "case", "catch"]
        count = sum(
            code.lower().count(keyword) for keyword in control_flow_keywords
        )

        # Normalize to 0-10 scale
        complexity = min(count / 5, 10.0)
        return round(complexity, 1)

    @staticmethod
    async def _calculate_security_score(issues: list[VerificationIssue]) -> float:
        """Calculate security score based on security-related issues."""
        security_issues = [
            i for i in issues if "security" in i.category.lower() or "injection" in i.title.lower()
        ]

        if not security_issues:
            return 10.0

        # Deduct points based on critical issues
        score = 10.0
        for issue in security_issues:
            if issue.severity == IssueSeverity.CRITICAL:
                score -= 5
            elif issue.severity == IssueSeverity.HIGH:
                score -= 2
            elif issue.severity == IssueSeverity.MEDIUM:
                score -= 1

        return max(score, 0.0)

    @staticmethod
    async def _calculate_performance_score(
        issues: list[VerificationIssue], code: str
    ) -> float:
        """Calculate performance score."""
        perf_issues = [i for i in issues if "performance" in i.category.lower() or "loop" in i.title.lower()]

        score = 10.0
        for issue in perf_issues:
            if issue.severity == IssueSeverity.CRITICAL:
                score -= 3
            elif issue.severity == IssueSeverity.HIGH:
                score -= 1.5
            elif issue.severity == IssueSeverity.MEDIUM:
                score -= 0.5

        return max(score, 0.0)

    @staticmethod
    async def _calculate_maintainability_score(
        issues: list[VerificationIssue], lines: int, complexity: float
    ) -> float:
        """Calculate maintainability score."""
        # Base score
        score = 10.0

        # Deduct for naming and documentation issues
        naming_issues = sum(1 for i in issues if "naming" in i.category.lower())
        doc_issues = sum(1 for i in issues if "documentation" in i.category.lower())

        score -= naming_issues * 0.5
        score -= doc_issues * 0.3

        # Deduct for complexity
        if complexity > 7:
            score -= 2
        elif complexity > 5:
            score -= 1

        # Deduct for file size
        if lines > 500:
            score -= 1
        elif lines > 300:
            score -= 0.5

        return max(score, 0.0)

    @staticmethod
    async def calculate_overall_quality_score(
        project_id: str,
        component_metrics: list[ComponentMetrics],
    ) -> QualityScore:
        """Calculate overall quality score for a project."""
        if not component_metrics:
            return QualityScore(
                project_id=project_id,
                overall_score=100.0,
                security_score=100.0,
                performance_score=100.0,
                maintainability_score=100.0,
                best_practices_score=100.0,
            )

        # Calculate average scores
        avg_security = sum(m.security_score for m in component_metrics) / len(component_metrics)
        avg_performance = sum(m.performance_score for m in component_metrics) / len(component_metrics)
        avg_maintainability = (
            sum(m.maintainability_score for m in component_metrics) / len(component_metrics)
        )

        # Calculate best practices score (based on issues)
        total_issues = sum(m.issue_count for m in component_metrics)
        total_lines = sum(m.total_lines for m in component_metrics)

        if total_lines > 0:
            issue_density = total_issues / (total_lines / 100)  # issues per 100 lines
            best_practices_score = max(10.0 - issue_density, 0.0)
        else:
            best_practices_score = 10.0

        # Weight scores
        overall_score = (
            avg_security * 0.3
            + avg_performance * 0.2
            + avg_maintainability * 0.3
            + best_practices_score * 0.2
        )

        return QualityScore(
            project_id=project_id,
            overall_score=round(overall_score * 10, 1),  # Scale to 0-100
            security_score=round(avg_security * 10, 1),
            performance_score=round(avg_performance * 10, 1),
            maintainability_score=round(avg_maintainability * 10, 1),
            best_practices_score=round(best_practices_score * 10, 1),
            component_metrics=component_metrics,
            breakdown={
                "security": round(avg_security * 10, 1),
                "performance": round(avg_performance * 10, 1),
                "maintainability": round(avg_maintainability * 10, 1),
                "best_practices": round(best_practices_score * 10, 1),
            },
        )

    @staticmethod
    async def determine_deployment_approval(
        quality_score: QualityScore,
        critical_issues: int,
        high_issues: int,
    ) -> tuple[bool, str]:
        """Determine if project is approved for deployment."""
        # Automatic rejection for critical issues
        if critical_issues > 0:
            reason = f"Project has {critical_issues} critical issue(s) that must be resolved"
            return False, reason

        # Automatic rejection for high issues > 5
        if high_issues > 5:
            reason = f"Project has {high_issues} high-severity issue(s), exceeds threshold of 5"
            return False, reason

        # Score-based approval
        if quality_score.overall_score < 60:
            reason = f"Overall quality score {quality_score.overall_score} is below minimum 60"
            return False, reason

        if quality_score.security_score < 60:
            reason = f"Security score {quality_score.security_score} is below minimum 60"
            return False, reason

        # Approved
        reason = "Project meets all deployment criteria"
        return True, reason
