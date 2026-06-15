"""Static analysis module for Verifier Agent."""

import re
import logging
from typing import Any

from salesforce_ai_engineer.verifier.models import (
    VerificationIssue,
    IssueCategory,
    IssueSeverity,
    ArtifactType,
)

logger = logging.getLogger(__name__)


class StaticAnalyzer:
    """Static code analysis for Salesforce artifacts."""

    SOQL_INJECTION_PATTERNS = [
        r"query\s*=\s*['\"][^'\"]*\+",
        r"\+\s*[a-zA-Z_]\w*",  # String concatenation
        r"Database\.query\s*\(",
    ]

    DANGEROUS_PATTERNS = [
        r"System\.debug\(.*\)",
        r"catch\s*\(\s*Exception\s*e\s*\)\s*\{[^}]*\}",
        r"while\s*\(true\)",
    ]

    DML_IN_LOOP_PATTERNS = [
        r"for\s*\([^)]*\)\s*\{[^}]*(insert|update|delete|upsert)[^}]*\}",
    ]

    NAMING_VIOLATIONS = {
        "variable": r"^[a-z][a-zA-Z0-9]*$",  # camelCase
        "constant": r"^[A-Z][A-Z0-9_]*$",  # UPPER_SNAKE
        "class": r"^[A-Z][a-zA-Z0-9]*$",  # PascalCase
    }

    @staticmethod
    async def analyze_apex_syntax(code: str, component_id: str) -> list[VerificationIssue]:
        """Analyze Apex code for syntax errors."""
        issues = []

        # Check for unclosed braces
        open_braces = code.count("{")
        close_braces = code.count("}")
        if open_braces != close_braces:
            issues.append(
                VerificationIssue(
                    artifact_id=component_id,
                    artifact_type=ArtifactType.APEX_CLASS,
                    category=IssueCategory.SYNTAX_ERROR,
                    severity=IssueSeverity.CRITICAL,
                    title="Mismatched braces",
                    description=f"Open braces: {open_braces}, Close braces: {close_braces}",
                    root_cause="Brace mismatch detected",
                    confidence=0.95,
                    recommendations=["Check for missing or extra braces"],
                )
            )

        # Check for unclosed parentheses
        open_parens = code.count("(")
        close_parens = code.count(")")
        if open_parens != close_parens:
            issues.append(
                VerificationIssue(
                    artifact_id=component_id,
                    artifact_type=ArtifactType.APEX_CLASS,
                    category=IssueCategory.SYNTAX_ERROR,
                    severity=IssueSeverity.CRITICAL,
                    title="Mismatched parentheses",
                    description=f"Open: {open_parens}, Close: {close_parens}",
                    root_cause="Parenthesis mismatch detected",
                    confidence=0.95,
                    recommendations=["Check method signatures and expressions"],
                )
            )

        return issues

    @staticmethod
    async def analyze_soql_injection_risk(code: str, component_id: str) -> list[VerificationIssue]:
        """Detect potential SOQL injection vulnerabilities."""
        issues = []

        # Check for string concatenation in SOQL queries
        if "query" in code.lower() and "+" in code and ("SELECT" in code or "select" in code):
            # Simple heuristic: if we have query + variable pattern
            if re.search(r"['\"].*\+.*['\"]", code):
                issues.append(
                    VerificationIssue(
                        artifact_id=component_id,
                        artifact_type=ArtifactType.APEX_CLASS,
                        category=IssueCategory.SECURITY,
                        severity=IssueSeverity.CRITICAL,
                        title="Potential SOQL Injection",
                        description="String concatenation detected in SOQL query",
                        location={"line": 1},
                        root_cause="Dynamic SOQL built with string concatenation",
                        confidence=0.85,
                        recommendations=[
                            "Use parameterized queries with bind variables",
                            "Use Database.query() with escaped parameters",
                        ],
                        affected_components=[component_id],
                        remediation_effort="medium",
                    )
                )
                return issues

        # Check for Database.query with string variable
        for match in re.finditer(r"Database\.query\s*\(\s*(\w+)\s*\)", code):
            var_name = match.group(1)
            # Check if this variable is built with concatenation
            if f"{var_name} =" in code and "+" in code:
                issues.append(
                    VerificationIssue(
                        artifact_id=component_id,
                        artifact_type=ArtifactType.APEX_CLASS,
                        category=IssueCategory.SECURITY,
                        severity=IssueSeverity.CRITICAL,
                        title="Potential SOQL Injection",
                        description=f"Variable {var_name} may be built with concatenation",
                        location={"line": code[:match.start()].count("\n") + 1},
                        root_cause="Dynamic SOQL built with string concatenation",
                        confidence=0.85,
                        recommendations=[
                            "Use parameterized queries with bind variables",
                            "Use Database.query() with escaped parameters",
                        ],
                        affected_components=[component_id],
                        remediation_effort="medium",
                    )
                )

        return issues

    @staticmethod
    async def analyze_dml_in_loop(code: str, component_id: str) -> list[VerificationIssue]:
        """Detect DML operations inside loops."""
        issues = []

        # Use pre-defined patterns to detect DML inside loop bodies across multiple lines
        for pattern in StaticAnalyzer.DML_IN_LOOP_PATTERNS:
            for match in re.finditer(pattern, code, re.IGNORECASE | re.DOTALL):
                line_no = code[:match.start()].count("\n") + 1
                issues.append(
                    VerificationIssue(
                        artifact_id=component_id,
                        artifact_type=ArtifactType.APEX_CLASS,
                        category=IssueCategory.GOVERNOR_LIMIT,
                        severity=IssueSeverity.HIGH,
                        title="DML operation inside loop",
                        description=f"DML operation detected inside loop body starting near line {line_no}",
                        location={"line": line_no},
                        root_cause="DML statements within loops consume governor limits per iteration",
                        confidence=0.85,
                        recommendations=[
                            "Collect records in a List and perform a single DML operation after the loop",
                            "Use Map collections if you need to associate records during processing",
                        ],
                        affected_components=[component_id],
                        remediation_effort="medium",
                    )
                )

        return issues

    @staticmethod
    async def analyze_crud_fls_compliance(code: str, component_id: str) -> list[VerificationIssue]:
        """Detect missing CRUD and FLS checks."""
        issues = []

        crud_keywords = ["insert", "update", "delete", "upsert"]
        soql_patterns = [r"SELECT.*FROM", r"\[SELECT"]

        # Check for SOQL without CRUD check
        has_crud_check = any(phrase in code for phrase in ["schema.sObjectType", "Schema.", "UserCanPerform"])
        has_soql = any(re.search(pattern, code) for pattern in soql_patterns)

        if has_soql and not has_crud_check:
            issues.append(
                VerificationIssue(
                    artifact_id=component_id,
                    artifact_type=ArtifactType.APEX_CLASS,
                    category=IssueCategory.CRUD_FLS,
                    severity=IssueSeverity.HIGH,
                    title="Missing CRUD/FLS checks",
                    description="SOQL queries found without CRUD/FLS validation",
                    root_cause="Code lacks permission validation before data access",
                    confidence=0.80,
                    recommendations=[
                        "Add schema.sObjectType.<Object>.isAccessible() checks",
                        "Add field-level security checks",
                        "Use WITH SECURITY_ENFORCED for SOQL",
                    ],
                    affected_components=[component_id],
                    remediation_effort="medium",
                )
            )

        return issues

    @staticmethod
    async def analyze_naming_conventions(code: str, artifact_type: ArtifactType) -> list[VerificationIssue]:
        """Detect naming convention violations.
        
        Args:
            code: The source code to analyze
            artifact_type: The type of artifact
        """
        issues = []

        # Extract class names
        class_matches = re.finditer(r"(?:public|private|global)\s+(?:class|interface)\s+([a-zA-Z_]\w*)", code)
        for match in class_matches:
            name = match.group(1)
            if not re.match(r"^[A-Z][a-zA-Z0-9]*$", name):
                issues.append(
                    VerificationIssue(
                        artifact_id=name,
                        artifact_type=artifact_type,
                        category=IssueCategory.NAMING_CONVENTION,
                        severity=IssueSeverity.LOW,
                        title=f"Class naming violation: {name}",
                        description=f"Class '{name}' does not follow PascalCase convention",
                        root_cause="Salesforce best practice requires PascalCase for class names",
                        confidence=0.95,
                        recommendations=["Rename class to follow PascalCase (e.g., MyClassName)"],
                        remediation_effort="low",
                    )
                )

        return issues

    @staticmethod
    async def analyze_lwc_structure(files: dict[str, str]) -> list[VerificationIssue]:
        """Analyze Lightning Web Component file structure."""
        issues = []

        required_files = ["js", "html"]
        present_types = set()

        for filename, content in files.items():
            if filename.endswith(".js"):
                present_types.add("js")
                # Check for basic LWC structure
                if "export default class" not in content:
                    issues.append(
                        VerificationIssue(
                            artifact_id=filename,
                            artifact_type=ArtifactType.LWC,
                            category=IssueCategory.SYNTAX_ERROR,
                            severity=IssueSeverity.HIGH,
                            title="Missing LWC export",
                            description="LWC component missing 'export default class'",
                            root_cause="LWC JavaScript must export default component class",
                            confidence=0.95,
                            recommendations=["Add proper LWC component export"],
                            remediation_effort="low",
                        )
                    )

            elif filename.endswith(".html"):
                present_types.add("html")

        for required in required_files:
            if required not in present_types:
                issues.append(
                    VerificationIssue(
                        artifact_id="lwc-structure",
                        artifact_type=ArtifactType.LWC,
                        category=IssueCategory.ARCHITECTURE,
                        severity=IssueSeverity.HIGH,
                        title=f"Missing LWC {required.upper()} file",
                        description=f"LWC component missing required .{required} file",
                        root_cause="LWC components require .js, .html, and .js-meta.xml files",
                        confidence=0.95,
                        recommendations=[f"Create .{required} file for component"],
                        remediation_effort="low",
                    )
                )

        return issues

    @staticmethod
    async def analyze_flow_logic(flow_xml: str, component_id: str) -> list[VerificationIssue]:
        """Analyze Flow XML for logical issues."""
        issues = []

        # Check for unconnected elements
        if "<decision>" in flow_xml and "<connector>" not in flow_xml:
            issues.append(
                VerificationIssue(
                    artifact_id=component_id,
                    artifact_type=ArtifactType.FLOW,
                    category=IssueCategory.LOGIC_ERROR,
                    severity=IssueSeverity.HIGH,
                    title="Unconnected decision element",
                    description="Decision element found without proper connectors",
                    root_cause="All Flow elements must be properly connected",
                    confidence=0.85,
                    recommendations=["Add connector elements to all decision paths"],
                    affected_components=[component_id],
                    remediation_effort="medium",
                )
            )

        return issues

    @staticmethod
    async def analyze_metadata_consistency(metadata: dict[str, Any], component_id: str) -> list[VerificationIssue]:
        """Analyze metadata for consistency issues."""
        issues = []

        # Check for required fields
        if "type" not in metadata:
            issues.append(
                VerificationIssue(
                    artifact_id=component_id,
                    artifact_type=ArtifactType.CUSTOM_OBJECT,
                    category=IssueCategory.METADATA_CONSISTENCY,
                    severity=IssueSeverity.CRITICAL,
                    title="Missing metadata type",
                    description="Metadata object missing required 'type' field",
                    root_cause="All metadata must specify a type",
                    confidence=0.95,
                    recommendations=["Add 'type' field to metadata"],
                    remediation_effort="low",
                )
            )

        if "name" not in metadata or not metadata.get("name"):
            issues.append(
                VerificationIssue(
                    artifact_id=component_id,
                    artifact_type=ArtifactType.CUSTOM_OBJECT,
                    category=IssueCategory.METADATA_CONSISTENCY,
                    severity=IssueSeverity.CRITICAL,
                    title="Missing metadata name",
                    description="Metadata object missing required 'name' field",
                    root_cause="All metadata must have a name",
                    confidence=0.95,
                    recommendations=["Add 'name' field to metadata"],
                    remediation_effort="low",
                )
            )

        return issues

    @staticmethod
    async def analyze_performance(code: str, component_id: str) -> list[VerificationIssue]:
        """Analyze code for performance issues."""
        issues = []

        # Check for inefficient SOQL
        if "SELECT * FROM" in code:
            issues.append(
                VerificationIssue(
                    artifact_id=component_id,
                    artifact_type=ArtifactType.APEX_CLASS,
                    category=IssueCategory.PERFORMANCE,
                    severity=IssueSeverity.MEDIUM,
                    title="Inefficient SOQL: SELECT *",
                    description="SOQL query using SELECT * instead of specific fields",
                    root_cause="SELECT * retrieves unnecessary fields",
                    confidence=0.90,
                    recommendations=[
                        "Specify only required fields in SELECT",
                        "This improves performance and reduces governor limit impact",
                    ],
                    remediation_effort="low",
                )
            )

        # Check for excessive logging
        debug_count = code.count("System.debug")
        if debug_count > 20:
            issues.append(
                VerificationIssue(
                    artifact_id=component_id,
                    artifact_type=ArtifactType.APEX_CLASS,
                    category=IssueCategory.PERFORMANCE,
                    severity=IssueSeverity.LOW,
                    title="Excessive debug logging",
                    description=f"Found {debug_count} debug statements",
                    root_cause="Excessive logging impacts performance",
                    confidence=0.80,
                    recommendations=["Remove or reduce debug statements in production code"],
                    remediation_effort="low",
                )
            )

        return issues
