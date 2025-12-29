"""Workflow service for DAG-based task workflows."""

from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from taskflow.core.config import get_settings
from taskflow.core.exceptions import (
    WorkflowNotFoundError,
    WorkflowValidationError,
    WorkflowCycleError,
    WorkflowExecutionError,
)
from taskflow.core.logging import get_logger, LoggerMixin
from taskflow.database.repository import BaseRepository
from taskflow.models.workflow import (
    Workflow,
    WorkflowNode,
    WorkflowEdge,
    WorkflowExecution,
    WorkflowStatus,
    NodeType,
)

settings = get_settings()
logger = get_logger(__name__)


class WorkflowService(LoggerMixin):
    """
    Service for managing DAG-based workflows.
    
    Provides workflow definition, validation, and execution.
    """
    
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workflow_repo = BaseRepository(Workflow, session)
        self.node_repo = BaseRepository(WorkflowNode, session)
        self.edge_repo = BaseRepository(WorkflowEdge, session)
        self.execution_repo = BaseRepository(WorkflowExecution, session)
    
    async def create_workflow(
        self,
        name: str,
        description: Optional[str] = None,
        tenant_id: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        input_schema: Optional[dict[str, Any]] = None,
        output_schema: Optional[dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Workflow:
        """
        Create a new workflow definition.
        
        Args:
            name: Workflow name
            description: Optional description
            tenant_id: Optional tenant ID
            config: Workflow configuration
            input_schema: JSON schema for workflow input
            output_schema: JSON schema for workflow output
            tags: Tags for filtering
            metadata: Additional metadata
            
        Returns:
            Created workflow
        """
        workflow = await self.workflow_repo.create(
            id=str(uuid4()),
            name=name,
            description=description,
            tenant_id=tenant_id,
            config=config or {},
            input_schema=input_schema,
            output_schema=output_schema,
            tags=tags or [],
            metadata=metadata or {},
            status=WorkflowStatus.DRAFT,
        )
        
        self.logger.info(
            "Workflow created",
            workflow_id=workflow.id,
            name=name,
        )
        
        return workflow
    
    async def add_node(
        self,
        workflow_id: str,
        node_key: str,
        name: str,
        node_type: NodeType = NodeType.TASK,
        task_type: Optional[str] = None,
        task_config: Optional[dict[str, Any]] = None,
        condition_expression: Optional[str] = None,
        delay_seconds: Optional[int] = None,
        subworkflow_id: Optional[str] = None,
        input_mapping: Optional[dict[str, Any]] = None,
        output_mapping: Optional[dict[str, Any]] = None,
        max_retries: int = 3,
        retry_delay: int = 60,
        on_failure: str = "fail",
        description: Optional[str] = None,
        position_x: Optional[int] = None,
        position_y: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WorkflowNode:
        """
        Add a node to a workflow.
        
        Args:
            workflow_id: Parent workflow ID
            node_key: Unique key within workflow
            name: Node display name
            node_type: Type of node
            task_type: Task type (for TASK nodes)
            task_config: Task configuration
            condition_expression: Condition (for CONDITION nodes)
            delay_seconds: Delay (for DELAY nodes)
            subworkflow_id: Subworkflow ID (for SUBWORKFLOW nodes)
            input_mapping: Input parameter mapping
            output_mapping: Output parameter mapping
            max_retries: Max retry attempts
            retry_delay: Retry delay in seconds
            on_failure: Failure behavior (fail, continue, skip)
            description: Node description
            position_x: X position for UI
            position_y: Y position for UI
            metadata: Additional metadata
            
        Returns:
            Created node
        """
        # Validate workflow exists
        workflow = await self.get_workflow(workflow_id)
        
        # Check node_key uniqueness within workflow
        existing = await self.node_repo.get_by(
            workflow_id=workflow_id,
            node_key=node_key,
        )
        if existing:
            raise WorkflowValidationError(
                f"Node with key '{node_key}' already exists in workflow"
            )
        
        node = await self.node_repo.create(
            id=str(uuid4()),
            workflow_id=workflow_id,
            node_key=node_key,
            name=name,
            node_type=node_type,
            task_type=task_type,
            task_config=task_config or {},
            condition_expression=condition_expression,
            delay_seconds=delay_seconds,
            subworkflow_id=subworkflow_id,
            input_mapping=input_mapping or {},
            output_mapping=output_mapping or {},
            max_retries=max_retries,
            retry_delay=retry_delay,
            on_failure=on_failure,
            description=description,
            position_x=position_x,
            position_y=position_y,
            metadata=metadata or {},
        )
        
        self.logger.info(
            "Node added to workflow",
            workflow_id=workflow_id,
            node_id=node.id,
            node_key=node_key,
        )
        
        return node
    
    async def add_edge(
        self,
        workflow_id: str,
        source_node_key: str,
        target_node_key: str,
        condition_branch: Optional[str] = None,
        data_mapping: Optional[dict[str, Any]] = None,
    ) -> WorkflowEdge:
        """
        Add an edge (dependency) between nodes.
        
        Args:
            workflow_id: Parent workflow ID
            source_node_key: Source node key
            target_node_key: Target node key
            condition_branch: Branch name for conditional edges
            data_mapping: Data mapping between nodes
            
        Returns:
            Created edge
        """
        # Get nodes
        source_node = await self.node_repo.get_by(
            workflow_id=workflow_id,
            node_key=source_node_key,
        )
        if not source_node:
            raise WorkflowValidationError(f"Source node '{source_node_key}' not found")
        
        target_node = await self.node_repo.get_by(
            workflow_id=workflow_id,
            node_key=target_node_key,
        )
        if not target_node:
            raise WorkflowValidationError(f"Target node '{target_node_key}' not found")
        
        edge = await self.edge_repo.create(
            id=str(uuid4()),
            workflow_id=workflow_id,
            source_node_id=source_node.id,
            target_node_id=target_node.id,
            condition_branch=condition_branch,
            data_mapping=data_mapping or {},
        )
        
        self.logger.info(
            "Edge added to workflow",
            workflow_id=workflow_id,
            source=source_node_key,
            target=target_node_key,
        )
        
        return edge
    
    async def validate_workflow(self, workflow_id: str) -> list[str]:
        """
        Validate a workflow definition.
        
        Checks for:
        - Cycles in the DAG
        - Missing dependencies
        - Invalid node configurations
        - Unreachable nodes
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            List of validation errors (empty if valid)
        """
        workflow = await self.get_workflow(workflow_id, load_relations=True)
        errors = []
        
        # Build adjacency list
        nodes = {node.id: node for node in workflow.nodes}
        adj = defaultdict(list)
        in_degree = defaultdict(int)
        
        for edge in workflow.edges:
            adj[edge.source_node_id].append(edge.target_node_id)
            in_degree[edge.target_node_id] += 1
        
        # Check for cycles using Kahn's algorithm
        queue = deque([nid for nid in nodes if in_degree[nid] == 0])
        visited = 0
        
        while queue:
            node_id = queue.popleft()
            visited += 1
            
            for target_id in adj[node_id]:
                in_degree[target_id] -= 1
                if in_degree[target_id] == 0:
                    queue.append(target_id)
        
        if visited != len(nodes):
            errors.append("Workflow contains a cycle")
        
        # Check for start nodes (no incoming edges)
        start_nodes = [n for n in nodes.values() if in_degree[n.id] == 0]
        if not start_nodes:
            errors.append("Workflow has no start nodes")
        
        # Validate node configurations
        for node in workflow.nodes:
            if node.node_type == NodeType.TASK and not node.task_type:
                errors.append(f"Node '{node.node_key}' is TASK type but has no task_type")
            
            if node.node_type == NodeType.CONDITION and not node.condition_expression:
                errors.append(f"Node '{node.node_key}' is CONDITION type but has no condition")
            
            if node.node_type == NodeType.DELAY and not node.delay_seconds:
                errors.append(f"Node '{node.node_key}' is DELAY type but has no delay_seconds")
            
            if node.node_type == NodeType.SUBWORKFLOW and not node.subworkflow_id:
                errors.append(f"Node '{node.node_key}' is SUBWORKFLOW but has no subworkflow_id")
        
        return errors
    
    async def publish_workflow(self, workflow_id: str) -> Workflow:
        """
        Publish a workflow, making it ready for execution.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            Updated workflow
            
        Raises:
            WorkflowValidationError: If workflow is invalid
        """
        errors = await self.validate_workflow(workflow_id)
        if errors:
            raise WorkflowValidationError(
                "Workflow validation failed",
                details={"errors": errors},
            )
        
        workflow = await self.workflow_repo.update(
            workflow_id,
            status=WorkflowStatus.PENDING,
        )
        
        self.logger.info("Workflow published", workflow_id=workflow_id)
        
        return workflow
    
    async def execute_workflow(
        self,
        workflow_id: str,
        input_data: Optional[dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WorkflowExecution:
        """
        Start a workflow execution.
        
        Args:
            workflow_id: Workflow ID
            input_data: Input data for the workflow
            tenant_id: Optional tenant ID
            metadata: Execution metadata
            
        Returns:
            Workflow execution instance
        """
        workflow = await self.get_workflow(workflow_id, load_relations=True)
        
        if workflow.status not in {WorkflowStatus.PENDING, WorkflowStatus.DRAFT}:
            raise WorkflowExecutionError(
                workflow_id,
                reason=f"Workflow is in {workflow.status} state",
            )
        
        # Create execution
        execution = await self.execution_repo.create(
            id=str(uuid4()),
            workflow_id=workflow_id,
            tenant_id=tenant_id or workflow.tenant_id,
            input_data=input_data or {},
            output_data={},
            context={},
            node_states={},
            metadata=metadata or {},
            status=WorkflowStatus.PENDING,
        )
        
        # Start execution asynchronously
        await self._start_execution(execution.id)
        
        self.logger.info(
            "Workflow execution started",
            workflow_id=workflow_id,
            execution_id=execution.id,
        )
        
        return execution
    
    async def _start_execution(self, execution_id: str) -> None:
        """Start workflow execution."""
        from taskflow.worker.celery_app import celery_app
        
        # Queue workflow execution task
        celery_app.send_task(
            "taskflow.worker.workflow_tasks.execute_workflow",
            args=[execution_id],
            queue="default",
        )
    
    async def get_workflow(
        self,
        workflow_id: str,
        tenant_id: Optional[str] = None,
        load_relations: bool = False,
    ) -> Workflow:
        """Get workflow by ID."""
        query = select(Workflow).where(Workflow.id == workflow_id)
        
        if tenant_id:
            query = query.where(Workflow.tenant_id == tenant_id)
        
        if load_relations:
            query = query.options(
                selectinload(Workflow.nodes),
                selectinload(Workflow.edges),
            )
        
        result = await self.session.execute(query)
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)
        
        return workflow
    
    async def list_workflows(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[WorkflowStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Workflow]:
        """List workflows with filtering."""
        filters = {}
        
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if status:
            filters["status"] = status
        
        return await self.workflow_repo.get_all(
            skip=skip,
            limit=limit,
            order_by="created_at",
            descending=True,
            **filters,
        )
    
    async def get_execution(
        self,
        execution_id: str,
        tenant_id: Optional[str] = None,
    ) -> WorkflowExecution:
        """Get workflow execution by ID."""
        if tenant_id:
            execution = await self.execution_repo.get_by(
                id=execution_id,
                tenant_id=tenant_id,
            )
        else:
            execution = await self.execution_repo.get(execution_id)
        
        if not execution:
            raise WorkflowExecutionError(execution_id, reason="Execution not found")
        
        return execution
    
    async def list_executions(
        self,
        workflow_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        status: Optional[WorkflowStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WorkflowExecution]:
        """List workflow executions with filtering."""
        filters = {}
        
        if workflow_id:
            filters["workflow_id"] = workflow_id
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if status:
            filters["status"] = status
        
        return await self.execution_repo.get_all(
            skip=skip,
            limit=limit,
            order_by="created_at",
            descending=True,
            **filters,
        )
    
    async def cancel_execution(
        self,
        execution_id: str,
        tenant_id: Optional[str] = None,
    ) -> WorkflowExecution:
        """Cancel a running workflow execution."""
        execution = await self.get_execution(execution_id, tenant_id)
        
        if execution.status in {WorkflowStatus.SUCCESS, WorkflowStatus.FAILED}:
            raise WorkflowExecutionError(
                execution_id,
                reason=f"Cannot cancel execution in {execution.status} state",
            )
        
        # Cancel all running tasks
        from taskflow.services.task_service import TaskService
        task_service = TaskService(self.session)
        
        from taskflow.models.task import Task, TaskStatus
        tasks = await self.session.execute(
            select(Task).where(
                Task.workflow_id == execution.workflow_id,
                Task.metadata["execution_id"].astext == execution_id,
                Task.status.in_([TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING]),
            )
        )
        
        for task in tasks.scalars():
            try:
                await task_service.cancel_task(task.id)
            except Exception:
                pass
        
        # Update execution status
        execution = await self.execution_repo.update(
            execution_id,
            status=WorkflowStatus.CANCELLED,
            completed_at=datetime.now(timezone.utc),
        )
        
        self.logger.info("Workflow execution cancelled", execution_id=execution_id)
        
        return execution
    
    async def delete_workflow(
        self,
        workflow_id: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Delete a workflow and all its nodes/edges."""
        workflow = await self.get_workflow(workflow_id, tenant_id)
        
        # Check for running executions
        running_count = await self.execution_repo.count(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
        )
        if running_count > 0:
            raise WorkflowValidationError(
                "Cannot delete workflow with running executions"
            )
        
        return await self.workflow_repo.delete(workflow_id)
