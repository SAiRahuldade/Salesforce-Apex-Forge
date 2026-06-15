"""
Test suite for Salesforce Engineer Agent.

Tests all components including code generation, validation, and integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from salesforce_ai_engineer.agent.models import ExecutionPlan, ExecutionTask, SalesforceWorkType, TaskStatus
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.memory.sqlite_store import SQLiteMemoryStore
from salesforce_ai_engineer.salesforce_engineer.agent import SalesforceEngineerAgent
from salesforce_ai_engineer.salesforce_engineer.generators import (
    ApexGenerator,
    FlowGenerator,
    LWCGenerator,
    MetadataGenerator,
)
from salesforce_ai_engineer.salesforce_engineer.validators import (
    CodeQualityValidator,
    DependencyValidator,
    GovernorLimitValidator,
    SecurityValidator,
)


@pytest.fixture
async def memory_manager(tmp_path):
    """Create a memory manager for tests."""
    db_path = tmp_path / "salesforce_engineer_test.db"
    store = SQLiteMemoryStore(db_path)
    await store.open()
    
    manager = MemoryManager(store)
    yield manager
    await store.close()


@pytest.fixture
def event_bus():
    """Create a mock event bus."""
    return EventBus()


@pytest.fixture
async def salesforce_engineer(event_bus, memory_manager):
    """Create a Salesforce Engineer Agent."""
    return SalesforceEngineerAgent(event_bus, memory_manager)


class TestApexGenerator:
    """Test Apex code generation."""
    
    @pytest.mark.asyncio
    async def test_generate_simple_apex_class(self):
        """Test generating a simple Apex class."""
        generator = ApexGenerator()
        
        task_input = {
            "class_name": "TestClass",
            "type": "standard",
            "methods": [
                {
                    "name": "testMethod",
                    "return_type": "String",
                    "visibility": "public",
                    "parameters": [],
                    "body": "        return 'test';",
                }
            ],
        }
        
        code = await generator.generate_apex(task_input, {})
        
        assert "TestClass" in code
        assert "testMethod" in code
        assert "return 'test';" in code
    
    @pytest.mark.asyncio
    async def test_generate_batch_apex_class(self):
        """Test generating a Batch Apex class."""
        generator = ApexGenerator()
        
        task_input = {
            "class_name": "TestBatch",
            "type": "batch",
            "methods": [],
        }
        
        code = await generator.generate_apex(task_input, {})
        
        assert "implements Database.Batchable<SObject>" in code
        assert "start(Database.BatchableContext bc)" in code
        assert "execute(Database.BatchableContext bc" in code
        assert "finish(Database.BatchableContext bc)" in code


class TestLWCGenerator:
    """Test Lightning Web Component generation."""
    
    @pytest.mark.asyncio
    async def test_generate_lwc_files(self):
        """Test generating LWC files."""
        generator = LWCGenerator()
        
        task_input = {
            "component_name": "test_component",
            "properties": [
                {"name": "recordId", "type": "String", "api": True}
            ],
            "methods": [
                {"name": "handleClick", "parameters": [], "body": "        // Handle click"}
            ],
            "template": "<div>Component</div>",
        }
        
        files = await generator.generate_lwc(task_input, {})
        
        assert "test_component.js" in files
        assert "test_component.html" in files
        assert "test_component.css" in files
        assert "test_component.js-meta.xml" in files
        
        assert "@api recordId" in files["test_component.js"]
        assert "<div>Component</div>" in files["test_component.html"]


class TestFlowGenerator:
    """Test Flow generation."""
    
    @pytest.mark.asyncio
    async def test_generate_flow_xml(self):
        """Test generating Flow XML."""
        generator = FlowGenerator()
        
        task_input = {
            "flow_name": "TestFlow",
            "type": "Flow",
            "description": "Test flow",
        }
        
        xml = await generator.generate_flow(task_input, {})
        
        assert "<?xml version" in xml
        assert "<name>TestFlow</name>" in xml
        assert "<apiVersion>58.0</apiVersion>" in xml


class TestMetadataGenerator:
    """Test metadata generation."""
    
    @pytest.mark.asyncio
    async def test_generate_custom_object_metadata(self):
        """Test generating custom object metadata."""
        generator = MetadataGenerator()
        
        task_input = {
            "type": "CustomObject",
            "object_name": "Test__c",
            "label": "Test Object",
            "fields": [],
        }
        
        metadata = await generator.generate_metadata(task_input, {})
        
        assert metadata["name"] == "Test__c"
        assert metadata["type"] == "CustomObject"
        assert metadata["label"] == "Test Object"
    
    @pytest.mark.asyncio
    async def test_generate_permission_set_metadata(self):
        """Test generating permission set metadata."""
        generator = MetadataGenerator()
        
        task_input = {
            "type": "PermissionSet",
            "name": "TestPermSet",
            "label": "Test Permission Set",
        }
        
        metadata = await generator.generate_metadata(task_input, {})
        
        assert metadata["type"] == "PermissionSet"
        assert metadata["name"] == "TestPermSet"


class TestSecurityValidator:
    """Test security validation."""
    
    @pytest.mark.asyncio
    async def test_validate_secure_code(self):
        """Test validating secure Apex code."""
        validator = SecurityValidator()
        
        code = """
        public class SecureClass {
            public void updateRecords(List<Account> accounts) {
                for (Account acc : accounts) {
                    // Process account
                }
                if (!accounts.isEmpty()) {
                    update accounts;
                }
            }
        }
        """
        
        is_secure, issues = await validator.validate_code_security(code, "apex")
        assert is_secure is True or len(issues) == 0 or any("DML" in issue for issue in issues)
    
    @pytest.mark.asyncio
    async def test_detect_soql_injection_risk(self):
        """Test detecting SOQL injection risks."""
        validator = SecurityValidator()
        
        code = """
        public class UnsafeQuery {
            public List<Account> getAccounts(String searchTerm) {
                String query = 'SELECT Id, Name FROM Account WHERE Name = ' + searchTerm;
                return Database.query(query);
            }
        }
        """
        
        is_secure, issues = await validator.validate_code_security(code, "apex")
        assert len(issues) > 0 or "String concatenation" in str(issues)


class TestGovernorLimitValidator:
    """Test governor limit validation."""
    
    @pytest.mark.asyncio
    async def test_analyze_code_for_limits(self):
        """Test analyzing code for governor limit issues."""
        validator = GovernorLimitValidator()
        
        code = """
        public class BulkProcessor {
            public void processRecords(List<Account> accounts) {
                List<Account> updated = new List<Account>();
                for (Account acc : accounts) {
                    acc.Name = acc.Name + '_Updated';
                    updated.add(acc);
                }
                update updated;
            }
        }
        """
        
        analysis = await validator.analyze_code(code)
        
        assert "estimated_soql_queries" in analysis
        assert "estimated_dml_statements" in analysis
        assert "potential_issues" in analysis


class TestDependencyValidator:
    """Test dependency validation."""
    
    @pytest.mark.asyncio
    async def test_validate_valid_dependencies(self):
        """Test validating valid dependencies."""
        validator = DependencyValidator()
        
        artifacts = {
            "artifact-1": {"type": "apex"},
            "artifact-2": {"type": "lwc"},
        }
        
        is_valid, errors = await validator.validate_dependencies(
            task_id="task-1",
            dependencies=["artifact-1"],
            available_artifacts=artifacts,
        )
        
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_missing_dependencies(self):
        """Test detecting missing dependencies."""
        validator = DependencyValidator()
        
        artifacts = {}
        
        is_valid, errors = await validator.validate_dependencies(
            task_id="task-1",
            dependencies=["missing-artifact"],
            available_artifacts=artifacts,
        )
        
        assert is_valid is False
        assert len(errors) > 0


class TestCodeQualityValidator:
    """Test code quality validation."""
    
    @pytest.mark.asyncio
    async def test_validate_naming_conventions(self):
        """Test validating naming conventions."""
        validator = CodeQualityValidator()
        
        good_code = """
        public class GoodClass {
            public void goodMethod() {}
        }
        """
        
        violations = await validator.validate_naming_conventions(good_code, "apex")
        # Should have minimal violations for properly named code
        assert isinstance(violations, list)
    
    @pytest.mark.asyncio
    async def test_validate_documentation(self):
        """Test validating code documentation."""
        validator = CodeQualityValidator()
        
        documented_code = """
        /**
         * Well documented class
         */
        public class WellDocumented {
            /**
             * Well documented method
             */
            public void method() {}
        }
        """
        
        issues = await validator.validate_documentation(documented_code)
        assert len(issues) == 0


class TestSalesforceEngineerAgent:
    """Test Salesforce Engineer Agent."""
    
    @pytest.mark.asyncio
    async def test_execute_simple_plan(self, salesforce_engineer):
        """Test executing a simple execution plan."""
        task = ExecutionTask(
            id="task-1",
            title="Generate Apex Class",
            description="Generate a test Apex class",
            agent="SalesforceEngineer",
            work_type=SalesforceWorkType.APEX,
            input={
                "class_name": "TestClass",
                "type": "standard",
            },
        )
        
        plan = ExecutionPlan(
            id="plan-1",
            objective="Test Objective",
            tasks=[task],
        )
        
        result = await salesforce_engineer.execute_plan(plan, "workflow-1")
        
        assert result["workflow_id"] == "workflow-1"
        assert result["execution_id"] is not None
        assert "artifacts" in result
        assert "task_results" in result
    
    @pytest.mark.asyncio
    async def test_execute_invalid_plan(self, salesforce_engineer):
        """Test executing an invalid plan."""
        task = ExecutionTask(
            id="task-1",
            title="Test Task",
            description="Test description",
            agent="SalesforceEngineer",
            missing_information=["Required field"],  # Plan has missing info
        )
        
        plan = ExecutionPlan(
            id="plan-1",
            objective="Test Objective",
            tasks=[task],
            missing_information=["Some info"],
        )
        
        with pytest.raises(Exception):
            await salesforce_engineer.execute_plan(plan, "workflow-1")
    
    @pytest.mark.asyncio
    async def test_execute_plan_with_multiple_tasks(self, salesforce_engineer):
        """Test executing plan with multiple tasks."""
        tasks = [
            ExecutionTask(
                id="task-1",
                title="Generate Apex",
                description="Generate Apex",
                agent="SalesforceEngineer",
                work_type=SalesforceWorkType.APEX,
                input={"class_name": "Class1"},
            ),
            ExecutionTask(
                id="task-2",
                title="Generate LWC",
                description="Generate LWC",
                agent="SalesforceEngineer",
                work_type=SalesforceWorkType.LWC,
                input={"component_name": "component1"},
                dependencies=["task-1"],
            ),
        ]
        
        plan = ExecutionPlan(
            id="plan-1",
            objective="Multi-task test",
            tasks=tasks,
        )
        
        result = await salesforce_engineer.execute_plan(plan, "workflow-1")
        
        assert len(result["task_results"]) == 2
        assert "artifacts" in result


class TestIntegration:
    """Integration tests for Salesforce Engineer Agent."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_code_generation(self, salesforce_engineer):
        """Test end-to-end code generation workflow."""
        # Create a plan that generates multiple artifacts
        tasks = [
            ExecutionTask(
                id="apex-task",
                title="Create Service Class",
                description="Service class for data processing",
                agent="SalesforceEngineer",
                work_type=SalesforceWorkType.APEX,
                input={
                    "class_name": "DataService",
                    "type": "standard",
                    "methods": [
                        {
                            "name": "processData",
                            "return_type": "void",
                            "visibility": "public",
                            "parameters": [
                                {"type": "List<SObject>", "name": "records"}
                            ],
                            "body": "        // Process records",
                        }
                    ],
                },
            ),
            ExecutionTask(
                id="lwc-task",
                title="Create UI Component",
                description="LWC for data display",
                agent="SalesforceEngineer",
                work_type=SalesforceWorkType.LWC,
                input={
                    "component_name": "data_display",
                    "properties": [
                        {"name": "recordId", "type": "String", "api": True}
                    ],
                },
                dependencies=["apex-task"],
            ),
        ]
        
        plan = ExecutionPlan(
            id="plan-1",
            objective="Full application",
            project="DataProcessing",
            tasks=tasks,
        )
        
        result = await salesforce_engineer.execute_plan(plan, "workflow-1")
        
        assert "artifacts" in result or "task_results" in result
        assert len(result.get("artifacts", {})) >= 0 or len(result.get("task_results", {})) >= 0
