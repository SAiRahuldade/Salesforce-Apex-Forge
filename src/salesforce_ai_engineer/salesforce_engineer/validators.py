"""
Validators for Salesforce artifacts.

Validates generated code for security, governor limits, dependencies,
and Salesforce best practices.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional


class DependencyValidator:
    """Validates task dependencies and prerequisites."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def validate_dependencies(
        self,
        task_id: str,
        dependencies: list[str],
        available_artifacts: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate that task dependencies are available.
        
        Args:
            task_id: Task identifier
            dependencies: List of dependency task IDs
            available_artifacts: Dictionary of available artifacts
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        for dependency_id in dependencies:
            if dependency_id not in available_artifacts:
                errors.append(f"Missing dependency: {dependency_id}")
        
        return len(errors) == 0, errors

    async def validate_prerequisites(
        self,
        task_input: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate that prerequisites are met.
        
        Args:
            task_input: Task input containing prerequisites
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        required_fields = task_input.get("required_fields", [])
        for field in required_fields:
            if field not in task_input:
                errors.append(f"Missing required field: {field}")
        
        return len(errors) == 0, errors


class SecurityValidator:
    """Validates generated code for security issues."""

    # Dangerous patterns that should not appear in code
    DANGEROUS_PATTERNS = [
        r"\'.*\' *\+ *[a-zA-Z_]",  # String concatenation in queries
        r"Database\.query\s*\(",  # Dynamic queries
        r"System\.execute.*",  # Dynamic execution
        r"Test\.stopTest\(\)",  # Test code in production
    ]

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def validate_code_security(
        self,
        code: str,
        code_type: str,
    ) -> tuple[bool, list[str]]:
        """Validate code for security issues.
        
        Args:
            code: Generated code to validate
            code_type: Type of code (apex, lwc, etc.)
            
        Returns:
            Tuple of (is_secure, security_issues)
        """
        issues = []
        
        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, code):
                issues.append(f"Potential security issue: {pattern}")
        
        # Check for SOQL injection risks
        if code_type == "apex":
            if "Database.query(" in code and "WITH SECURITY_ENFORCED" not in code:
                issues.append("SOQL query should use WITH SECURITY_ENFORCED")
        
        # Check for missing CRUD/FLS checks
        if "insert" in code or "update" in code or "delete" in code:
            if "Schema.SObjectType" not in code:
                issues.append("Missing CRUD/FLS check for DML operation")
        
        return len(issues) == 0, issues

    async def validate_governor_limits(
        self,
        code: str,
    ) -> tuple[bool, list[str]]:
        """Validate code for potential governor limit violations.
        
        Args:
            code: Generated code to validate
            
        Returns:
            Tuple of (is_valid, limit_warnings)
        """
        warnings = []
        
        # Check for loops with DML
        if re.search(r"for\s*\([^)]*\)\s*\{[^}]*(insert|update|delete|Database\.(insert|update|delete))", code):
            warnings.append("DML operation inside loop detected - consider bulkification")
        
        # Check for bulk operations outside transactions
        if code.count("insert ") > 1 and "Database.insert(" not in code:
            warnings.append("Multiple insert statements - consider using bulk operations")
        
        return len(warnings) == 0, warnings

    async def validate_and_generate_security(
        self,
        task_input: dict[str, Any],
        artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate artifacts and generate security configuration.
        
        Args:
            task_input: Task input containing security specification
            artifacts: Generated artifacts to validate
            
        Returns:
            Security configuration
        """
        security_config = {
            "permission_sets": task_input.get("permission_sets", []),
            "sharing_rules": task_input.get("sharing_rules", []),
            "field_level_security": task_input.get("field_level_security", []),
            "object_level_security": task_input.get("object_level_security", []),
            "validation_results": {},
        }
        
        # Validate each artifact
        for artifact_id, artifact in artifacts.items():
            if artifact.get("type") == "apex":
                is_secure, issues = await self.validate_code_security(
                    artifact.get("code", ""),
                    "apex",
                )
                security_config["validation_results"][artifact_id] = {
                    "is_secure": is_secure,
                    "issues": issues,
                }
        
        return security_config


class GovernorLimitValidator:
    """Validates code for Salesforce governor limit compliance."""

    # Governor limit thresholds
    LIMITS = {
        "soql_queries": 100,
        "dml_statements": 150,
        "heap_size": 6000000,  # 6MB
        "cpu_time": 10000,  # 10 seconds
        "callouts": 100,
        "code_unit_size": 6000000,
    }

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def analyze_code(
        self,
        code: str,
    ) -> dict[str, Any]:
        """Analyze code for governor limit usage.
        
        Args:
            code: Code to analyze
            
        Returns:
            Analysis results
        """
        analysis = {
            "estimated_soql_queries": len(re.findall(r"\[SELECT", code)),
            "estimated_dml_statements": len(
                re.findall(r"(insert|update|delete|upsert|Database\.(insert|update|delete|upsert))", code)
            ),
            "estimated_code_size": len(code),
            "potential_issues": [],
        }
        
        # Check for potential issues
        if analysis["estimated_soql_queries"] > 20:
            analysis["potential_issues"].append(
                f"High SOQL query count: {analysis['estimated_soql_queries']}"
            )
        
        if analysis["estimated_dml_statements"] > 50:
            analysis["potential_issues"].append(
                f"High DML statement count: {analysis['estimated_dml_statements']}"
            )
        
        if analysis["estimated_code_size"] > 3000000:
            analysis["potential_issues"].append("Large code size detected")
        
        return analysis


class CodeQualityValidator:
    """Validates code quality and best practices."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def validate_naming_conventions(
        self,
        code: str,
        code_type: str,
    ) -> list[str]:
        """Validate Salesforce naming conventions.
        
        Args:
            code: Code to validate
            code_type: Type of code
            
        Returns:
            List of naming convention violations
        """
        violations = []
        
        if code_type == "apex":
            # Class names should be PascalCase
            class_pattern = r"class\s+([a-z][\w]*)"
            if re.search(class_pattern, code):
                violations.append("Class names should use PascalCase")
            
            # Method names should be camelCase
            method_pattern = r"(public|private|protected)\s+\w+\s+([A-Z][\w]*)\("
            if re.search(method_pattern, code):
                violations.append("Method names should use camelCase")
        
        return violations

    async def validate_documentation(
        self,
        code: str,
    ) -> list[str]:
        """Validate code documentation.
        
        Args:
            code: Code to validate
            
        Returns:
            List of documentation issues
        """
        issues = []
        
        # Count class definitions vs comments
        classes = len(re.findall(r"class\s+\w+", code))
        comments = len(re.findall(r"//|/\*", code))
        
        if classes > 0 and comments < classes:
            issues.append(f"Some classes lack documentation (found {comments} comments, {classes} classes)")
        
        return issues
