"""
Salesforce Engineer Agent - Transforms execution plans into production-ready Salesforce solutions.

This agent is responsible for code generation, metadata creation, validation,
and integration with the Salesforce platform. It follows best practices for
governor limits, security, bulkification, and maintainability.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from salesforce_ai_engineer.agent.models import (
    ExecutionPlan,
    ExecutionTask,
    SalesforceWorkType,
    TaskStatus,
    TaskResult,
)
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.models.domain.shared import ToolResponse, ToolStatus
from salesforce_ai_engineer.tools.executor import ToolExecutor


class SalesforceEngineerError(RuntimeError):
    """Raised when Salesforce Engineer Agent encounters an error."""


class SalesforceEngineerAgent:
    """Autonomous agent for generating production-ready Salesforce solutions."""

    def __init__(
        self,
        event_bus: EventBus,
        memory_manager: MemoryManager,
        logger: Optional[logging.Logger] = None,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        """Initialize the Salesforce Engineer Agent.
        
        Args:
            event_bus: Event system for lifecycle events
            memory_manager: Memory system for storing generated knowledge
            logger: Optional logger instance
            tool_executor: Optional tool executor for filesystem and external access
        """
        self.event_bus = event_bus
        self.memory_manager = memory_manager
        self.logger = logger or logging.getLogger(__name__)
        self.tool_executor = tool_executor

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        workflow_id: str,
    ) -> dict[str, Any]:
        """Execute an execution plan and generate Salesforce solutions.
        
        Args:
            plan: Execution plan from Planner
            workflow_id: Workflow identifier for tracking
            
        Returns:
            Dictionary containing generated artifacts and metadata
        """
        try:
            self.logger.info(f"Starting plan execution for workflow {workflow_id}")
            
            # Validate the plan
            if not plan.is_ready:
                raise SalesforceEngineerError(
                    f"Plan not ready for execution. Missing information: "
                    f"{plan.missing_information}"
                )
            
            # Emit execution started event
            await self.event_bus.publish(
                "salesforce_engineer.execution_started",
                {
                    "workflow_id": workflow_id,
                    "plan_id": plan.id,
                    "task_count": len(plan.tasks),
                    "objective": plan.objective,
                },
            )
            
            # Execute tasks in dependency order
            generated_artifacts = {}
            task_results = {}
            
            for task in plan.tasks:
                self.logger.debug(f"Executing task {task.id}: {task.title}")
                
                try:
                    result = await self._execute_task(
                        task=task,
                        plan=plan,
                        workflow_id=workflow_id,
                        generated_artifacts=generated_artifacts,
                    )
                    
                    task_results[task.id] = result
                    if result.get("status") == "success":
                        generated_artifacts.update(result.get("artifacts", {}))
                    
                except Exception as e:
                    self.logger.error(f"Task execution failed: {e}", exc_info=True)
                    task_results[task.id] = {
                        "status": "failed",
                        "error": str(e),
                    }
            
            # Store execution record in memory
            execution_id = await self.memory_manager.store_completed_task(
                task_type="SalesforceProjectExecution",
                task_id=f"exec-{workflow_id}",
                agent_responsible="SalesforceEngineer",
                approach_used="ExecutionPlanBased",
                result_summary=f"Generated {len(generated_artifacts)} artifacts",
                success=all(r.get("status") == "success" for r in task_results.values()),
                duration_seconds=0,  # Would be calculated in production
                created_by="orchestrator",
            )
            
            # Emit execution completed event
            await self.event_bus.publish(
                "salesforce_engineer.execution_completed",
                {
                    "workflow_id": workflow_id,
                    "plan_id": plan.id,
                    "execution_id": execution_id,
                    "artifacts_count": len(generated_artifacts),
                    "success": all(r.get("status") == "success" for r in task_results.values()),
                },
            )
            
            return {
                "workflow_id": workflow_id,
                "execution_id": execution_id,
                "artifacts": generated_artifacts,
                "task_results": task_results,
                "metadata": {
                    "plan_id": plan.id,
                    "project": plan.objective,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            }
        
        except Exception as e:
            self.logger.error(f"Plan execution failed: {e}", exc_info=True)
            await self.event_bus.publish(
                "salesforce_engineer.execution_failed",
                {
                    "workflow_id": workflow_id,
                    "error": str(e),
                },
            )
            raise

    async def _execute_task(
        self,
        task: ExecutionTask,
        plan: ExecutionPlan,
        workflow_id: str,
        generated_artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single task and generate artifacts.
        
        Args:
            task: Task to execute
            plan: Parent execution plan
            workflow_id: Workflow identifier
            generated_artifacts: Previously generated artifacts
            
        Returns:
            Task result with generated artifacts
        """
        from salesforce_ai_engineer.salesforce_engineer.generators import (
            ApexGenerator,
            FlowGenerator,
            LWCGenerator,
            MetadataGenerator,
        )
        from salesforce_ai_engineer.salesforce_engineer.validators import (
            DependencyValidator,
            SecurityValidator,
        )
        
        # Route to appropriate handler based on work type
        handlers = {
            SalesforceWorkType.APEX: self._handle_apex_task,
            SalesforceWorkType.LWC: self._handle_lwc_task,
            SalesforceWorkType.FLOW: self._handle_flow_task,
            SalesforceWorkType.METADATA_GENERATION: self._handle_metadata_task,
            SalesforceWorkType.SECURITY: self._handle_security_task,
            SalesforceWorkType.DEPLOYMENT: self._handle_deployment_task,
            SalesforceWorkType.SALESFORCE_PROJECT: self._handle_project_task,
        }
        
        handler = handlers.get(task.work_type, self._handle_project_task)
        return await handler(task, plan, workflow_id, generated_artifacts)

    async def _handle_apex_task(
        self,
        task: ExecutionTask,
        plan: ExecutionPlan,
        workflow_id: str,
        generated_artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle Apex code generation task."""
        from salesforce_ai_engineer.salesforce_engineer.generators import ApexGenerator
        
        generator = ApexGenerator(self.logger)
        
        try:
            code = await generator.generate_apex(
                task_input=task.input,
                context=plan.metadata,
            )
            
            artifact_id = f"apex-{uuid4()}"
            
            await self.memory_manager.store_completed_task(
                task_type="ApexGeneration",
                task_id=artifact_id,
                agent_responsible="SalesforceEngineer",
                approach_used=task.input.get("approach", "default"),
                result_summary=f"Generated Apex class",
                success=True,
                duration_seconds=0,
                created_by="salesforce_engineer",
            )
            
            return {
                "status": "success",
                "task_id": task.id,
                "artifacts": {
                    artifact_id: {
                        "type": "apex",
                        "code": code,
                        "metadata": task.input,
                    }
                },
            }
        except Exception as e:
            self.logger.error(f"Apex generation failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "task_id": task.id,
                "error": str(e),
            }

    async def _handle_lwc_task(
        self,
        task: ExecutionTask,
        plan: ExecutionPlan,
        workflow_id: str,
        generated_artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle Lightning Web Component generation task."""
        from salesforce_ai_engineer.salesforce_engineer.generators import LWCGenerator
        
        generator = LWCGenerator(self.logger)
        
        try:
            components = await generator.generate_lwc(
                task_input=task.input,
                context=plan.metadata,
            )
            
            artifacts = {}
            for component_name, component_code in components.items():
                artifact_id = f"lwc-{uuid4()}"
                artifacts[artifact_id] = {
                    "type": "lwc",
                    "name": component_name,
                    "code": component_code,
                    "metadata": task.input,
                }
            
            return {
                "status": "success",
                "task_id": task.id,
                "artifacts": artifacts,
            }
        except Exception as e:
            self.logger.error(f"LWC generation failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "task_id": task.id,
                "error": str(e),
            }

    async def _handle_flow_task(
        self,
        task: ExecutionTask,
        plan: ExecutionPlan,
        workflow_id: str,
        generated_artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle Flow generation task."""
        from salesforce_ai_engineer.salesforce_engineer.generators import FlowGenerator
        
        generator = FlowGenerator(self.logger)
        
        try:
            flow_xml = await generator.generate_flow(
                task_input=task.input,
                context=plan.metadata,
            )
            
            artifact_id = f"flow-{uuid4()}"
            
            return {
                "status": "success",
                "task_id": task.id,
                "artifacts": {
                    artifact_id: {
                        "type": "flow",
                        "xml": flow_xml,
                        "metadata": task.input,
                    }
                },
            }
        except Exception as e:
            self.logger.error(f"Flow generation failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "task_id": task.id,
                "error": str(e),
            }

    async def _handle_metadata_task(
        self,
        task: ExecutionTask,
        plan: ExecutionPlan,
        workflow_id: str,
        generated_artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle metadata generation task."""
        from salesforce_ai_engineer.salesforce_engineer.generators import MetadataGenerator
        
        generator = MetadataGenerator(self.logger)
        
        try:
            metadata = await generator.generate_metadata(
                task_input=task.input,
                context=plan.metadata,
            )
            
            artifact_id = f"metadata-{uuid4()}"
            
            return {
                "status": "success",
                "task_id": task.id,
                "artifacts": {
                    artifact_id: {
                        "type": "metadata",
                        "definition": metadata,
                        "metadata": task.input,
                    }
                },
            }
        except Exception as e:
            self.logger.error(f"Metadata generation failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "task_id": task.id,
                "error": str(e),
            }

    async def _handle_security_task(
        self,
        task: ExecutionTask,
        plan: ExecutionPlan,
        workflow_id: str,
        generated_artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle security validation and setup task."""
        from salesforce_ai_engineer.salesforce_engineer.validators import SecurityValidator
        
        validator = SecurityValidator(self.logger)
        
        try:
            security_config = await validator.validate_and_generate_security(
                task_input=task.input,
                artifacts=generated_artifacts,
            )
            
            artifact_id = f"security-{uuid4()}"
            
            return {
                "status": "success",
                "task_id": task.id,
                "artifacts": {
                    artifact_id: {
                        "type": "security",
                        "configuration": security_config,
                        "metadata": task.input,
                    }
                },
            }
        except Exception as e:
            self.logger.error(f"Security validation failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "task_id": task.id,
                "error": str(e),
            }

    async def _handle_deployment_task(
        self,
        task: ExecutionTask,
        plan: ExecutionPlan,
        workflow_id: str,
        generated_artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle deployment configuration task."""
        try:
            deployment_manifest = {
                "package": task.input.get("package_name", "SalesforceProject"),
                "version": task.input.get("version", "1.0.0"),
                "artifacts": [
                    {
                        "id": artifact_id,
                        "type": artifact.get("type"),
                    }
                    for artifact_id, artifact in generated_artifacts.items()
                ],
                "deployment_options": task.input.get("options", {}),
            }
            
            artifact_id = f"deployment-{uuid4()}"
            
            return {
                "status": "success",
                "task_id": task.id,
                "artifacts": {
                    artifact_id: {
                        "type": "deployment",
                        "manifest": deployment_manifest,
                        "metadata": task.input,
                    }
                },
            }
        except Exception as e:
            self.logger.error(f"Deployment configuration failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "task_id": task.id,
                "error": str(e),
            }

    async def _handle_project_task(
        self,
        task: ExecutionTask,
        plan: ExecutionPlan,
        workflow_id: str,
        generated_artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle overall project generation task."""
        try:
            project_structure = {
                "project_name": task.input.get("project_name", "SalesforceProject"),
                "description": task.input.get("description", ""),
                "artifacts_generated": len(generated_artifacts),
                "structure": {
                    "src": {
                        "classes": [],
                        "components": [],
                        "flows": [],
                        "objects": [],
                    },
                    "metadata": {},
                    "tests": [],
                },
            }
            
            artifact_id = f"project-{uuid4()}"
            
            return {
                "status": "success",
                "task_id": task.id,
                "artifacts": {
                    artifact_id: {
                        "type": "project",
                        "structure": project_structure,
                        "metadata": task.input,
                    }
                },
            }
        except Exception as e:
            self.logger.error(f"Project generation failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "task_id": task.id,
                "error": str(e),
            }

    async def execute(self, task: ExecutionTask) -> TaskResult:
        """Execute a single workflow task and return structured artifacts."""

        plan = ExecutionPlan(
            objective=task.description or task.title,
            tasks=[task.model_copy(deep=True)],
        )
        workflow_id = str(task.input.get("workflow_id") or "unknown")
        result = await self._execute_task(
            task=task,
            plan=plan,
            workflow_id=workflow_id,
            generated_artifacts=dict(task.input.get("artifacts", {})),
        )
        if result.get("status") == "success":
            return TaskResult(
                task_id=task.id,
                success=True,
                output={
                    "artifacts": result.get("artifacts", {}),
                    "summary": result.get("summary", task.title),
                },
            )
        return TaskResult(
            task_id=task.id,
            success=False,
            error=result.get("error", "Salesforce engineer task failed"),
            output=result,
        )
