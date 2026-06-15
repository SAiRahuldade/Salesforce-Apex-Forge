"""Utility module for constructing and handling Directed Acyclic Graphs (DAGs)
used by the Salesforce AI Engineer workflow engine.

The engine already provides a generic ``SchedulingStrategy`` that can fetch
runnable tasks based on their dependencies.  Phase 2 introduces a clearer
abstraction – a lightweight ``DAG`` class that can be built from an
``ExecutionPlan`` and later queried for ready tasks, cycle detection, and
dynamic task insertion (generated tasks).

Only standard library imports are used so the module is safe to import in any
environment.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, Iterable, List, Set

from salesforce_ai_engineer.agent.models import ExecutionPlan, ExecutionTask


class DAGError(RuntimeError):
    """Base class for DAG‑related errors."""


class CycleError(DAGError):
    """Raised when a cycle is detected while building the graph."""


class DAG:
    """Simple in‑memory representation of a directed acyclic graph.

    The graph is *task‑centric*: each node is the ``id`` of an
    :class:`~salesforce_ai_engineer.agent.models.ExecutionTask`.  Edges point
    from a *dependency* to the *dependent* task – i.e. ``A -> B`` means *B* cannot
    run until *A* has succeeded.

    The class provides:

    * :meth:`add_task` – registers a task and its dependencies.
    * :meth:`add_generated_task` – inserts a task discovered at runtime (used by
      ``WorkflowEngine._apply_dynamic_tasks``).
    * :meth:`ready_tasks` – returns the set of task ids whose dependencies are
      satisfied and that are not yet marked *completed*.
    * :meth:`detect_cycle` – validates the graph on construction.
    """

    def __init__(self) -> None:
        # adjacency list: node -> set of dependent nodes
        self._graph: Dict[str, Set[str]] = defaultdict(set)
        # reverse adjacency: node -> set of prerequisite nodes
        self._reverse: Dict[str, Set[str]] = defaultdict(set)
        # all known node ids (including leaf nodes with no edges)
        self._nodes: Set[str] = set()
        # tasks that have already completed – supplied by the engine
        self._completed: Set[str] = set()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def add_task(self, task: ExecutionTask) -> None:
        """Register ``task`` and its declared ``dependencies``.

        If the addition would create a cycle, :class:`CycleError` is raised.
        """
        self._nodes.add(task.id)
        for dep in task.dependencies:
            self._graph[dep].add(task.id)
            self._reverse[task.id].add(dep)
            self._nodes.add(dep)
        # ensure every node appears in both dicts even if it has no edges
        self._graph.setdefault(task.id, set())
        self._reverse.setdefault(task.id, set())
        self._detect_cycle()

    def add_generated_task(self, task: ExecutionTask) -> None:
        """Insert a task that was produced at runtime.

        The method mirrors :meth:`add_task` but does **not** perform a cycle
        check that would reject the generated task – the engine already validates
        dependencies before calling this method.  Nonetheless we keep the same
        internal structure.
        """
        self._nodes.add(task.id)
        for dep in task.dependencies:
            self._graph[dep].add(task.id)
            self._reverse[task.id].add(dep)
            self._nodes.add(dep)
        self._graph.setdefault(task.id, set())
        self._reverse.setdefault(task.id, set())
        # Cycle detection is optional for generated tasks; failure would be a
        # programming error, so we raise if it occurs.
        self._detect_cycle()

    def mark_completed(self, task_id: str) -> None:
        """Record that ``task_id`` has finished successfully."""
        self._completed.add(task_id)

    def ready_tasks(self, running_task_ids: Iterable[str] = ()) -> List[str]:
        """Return a list of task ids ready to run.

        * ``running_task_ids`` – tasks that are already dispatched; they are
          ignored for the readiness calculation but are kept out of the result.
        """
        running = set(running_task_ids)
        ready: List[str] = []
        for node in self._nodes:
            if node in self._completed or node in running:
                continue
            # a node is ready when all its prerequisites are completed
            if self._reverse[node].issubset(self._completed):
                ready.append(node)
        return ready

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _detect_cycle(self) -> None:
        """Perform a DFS based cycle check; raise :class:`CycleError` on failure.
        """
        visited: Set[str] = set()
        stack: Set[str] = set()

        def visit(n: str) -> None:
            if n in stack:
                raise CycleError(f"Cycle detected involving task {n!r}")
            if n in visited:
                return
            stack.add(n)
            for neighbour in self._graph.get(n, []):
                visit(neighbour)
            stack.remove(n)
            visited.add(n)

        for node in self._nodes:
            visit(node)

    # ---------------------------------------------------------------------
    # Convenience constructors
    # ---------------------------------------------------------------------
    @classmethod
    def from_plan(cls, plan: ExecutionPlan) -> "DAG":
        """Build a :class:`DAG` from an :class:`ExecutionPlan`.

        The method iterates over ``plan.tasks`` and registers each task with its
        declared dependencies.  If a cycle is present the construction fails with
        :class:`CycleError` – this mirrors the behaviour expected by the engine
        when a user submits an invalid workflow.
        """
        dag = cls()
        for task in plan.tasks:
            dag.add_task(task)
        return dag

    # ---------------------------------------------------------------------
    # Debug helpers
    # ---------------------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover – simple debugging aid
        return (
            f"DAG(nodes={len(self._nodes)}, edges={sum(len(v) for v in self._graph.values())}, "
            f"completed={len(self._completed)})"
        )
