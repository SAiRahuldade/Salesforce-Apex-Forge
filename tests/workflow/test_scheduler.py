import pytest
from salesforce_ai_engineer.agent.models import ExecutionPlan, ExecutionTask, TaskStatus
from salesforce_ai_engineer.workflow.scheduler import TopologicalSchedulingStrategy

def test_topological_scheduler_no_dependencies():
    scheduler = TopologicalSchedulingStrategy()
    plan = ExecutionPlan(
        objective="Test",
        tasks=[
            ExecutionTask(title="Task 1", description="1", agent="test"),
            ExecutionTask(title="Task 2", description="2", agent="test"),
        ]
    )
    
    ready = scheduler.ready_tasks(plan, set())
    assert len(ready) == 2
    assert {t.id for t in ready} == {plan.tasks[0].id, plan.tasks[1].id}

def test_topological_scheduler_with_dependencies():
    scheduler = TopologicalSchedulingStrategy()
    t1 = ExecutionTask(id="1", title="Task 1", description="1", agent="test")
    t2 = ExecutionTask(id="2", title="Task 2", description="2", agent="test", dependencies=["1"])
    t3 = ExecutionTask(id="3", title="Task 3", description="3", agent="test", dependencies=["1", "2"])
    
    plan = ExecutionPlan(objective="Test", tasks=[t1, t2, t3])
    
    # Initially only t1 is ready
    ready = scheduler.ready_tasks(plan, set())
    assert len(ready) == 1
    assert ready[0].id == "1"
    
    # If t1 is running, none are ready
    ready = scheduler.ready_tasks(plan, {"1"})
    assert len(ready) == 0
    
    # If t1 succeeds, t2 is ready
    t1.status = TaskStatus.SUCCESS
    ready = scheduler.ready_tasks(plan, set())
    assert len(ready) == 1
    assert ready[0].id == "2"
    
    # If t2 is running, none are ready
    ready = scheduler.ready_tasks(plan, {"2"})
    assert len(ready) == 0
    
    # If t2 succeeds, t3 is ready
    t2.status = TaskStatus.SUCCESS
    ready = scheduler.ready_tasks(plan, set())
    assert len(ready) == 1
    assert ready[0].id == "3"

def test_topological_scheduler_failed_dependency():
    scheduler = TopologicalSchedulingStrategy()
    t1 = ExecutionTask(id="1", title="Task 1", description="1", agent="test")
    t2 = ExecutionTask(id="2", title="Task 2", description="2", agent="test", dependencies=["1"])
    
    plan = ExecutionPlan(objective="Test", tasks=[t1, t2])
    
    # If t1 fails, t2 should not be ready
    t1.status = TaskStatus.FAILED
    ready = scheduler.ready_tasks(plan, set())
    assert len(ready) == 0
