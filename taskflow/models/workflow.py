"""Workflow models for DAG-based task dependencies."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskflow.models.base import Base, TimestampMixin


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    
    DRAFT = "draft"         # Workflow being defined
    PENDING = "pending"     # Ready to start
    RUNNING = "running"     # Currently executing
    PAUSED = "paused"       # Execution paused
    SUCCESS = "success"     # All tasks completed successfully
    PARTIAL = "partial"     # Some tasks failed, but workflow continued
    FAILED = "failed"       # Workflow failed
    CANCELLED = "cancelled" # Workflow was cancelled


class NodeType(str, Enum):
    """Type of workflow node."""
    
    TASK = "task"           # Execute a task
    PARALLEL = "parallel"   # Run children in parallel
    CONDITION = "condition" # Conditional branching
    DELAY = "delay"         # Wait for specified time
    WEBHOOK = "webhook"     # Wait for external trigger
    SUBWORKFLOW = "subworkflow"  # Execute another workflow


class Workflow(Base, TimestampMixin):
    """
    Represents a workflow definition (DAG of tasks).
    
    Workflows define a directed acyclic graph of tasks with
    dependencies, conditions, and parallel execution.
    """
    
    __tablename__ = "workflows"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    # Workflow identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Multi-tenancy
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    
    # Status
    status: Mapped[WorkflowStatus] = mapped_column(
        String(50),
        default=WorkflowStatus.DRAFT,
        nullable=False,
        index=True,
    )
    is_template: Mapped[bool] = mapped_column(default=False, nullable=False)
    
    # Configuration
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Input/output schema
    input_schema: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    output_schema: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Default values
    default_timeout: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    
    # Metadata
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Relationships
    nodes: Mapped[list["WorkflowNode"]] = relationship(
        "WorkflowNode",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    edges: Mapped[list["WorkflowEdge"]] = relationship(
        "WorkflowEdge",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    executions: Mapped[list["WorkflowExecution"]] = relationship(
        "WorkflowExecution",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Workflow(id={self.id}, name={self.name}, v{self.version})>"


class WorkflowNode(Base, TimestampMixin):
    """
    Represents a node in a workflow DAG.
    
    Each node can be a task, parallel group, condition, delay, etc.
    """
    
    __tablename__ = "workflow_nodes"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    workflow_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Node identification
    node_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Node type
    node_type: Mapped[NodeType] = mapped_column(
        String(50),
        default=NodeType.TASK,
        nullable=False,
    )
    
    # Task configuration (for TASK type)
    task_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    task_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Condition configuration (for CONDITION type)
    condition_expression: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Delay configuration (for DELAY type)
    delay_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Subworkflow configuration (for SUBWORKFLOW type)
    subworkflow_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflows.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Input/output mapping
    input_mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    output_mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Retry configuration
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    retry_delay: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    
    # Error handling
    on_failure: Mapped[str] = mapped_column(String(50), default="fail", nullable=False)
    
    # UI positioning
    position_x: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position_y: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Metadata
    metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="nodes")
    
    def __repr__(self) -> str:
        return f"<WorkflowNode(id={self.id}, key={self.node_key}, type={self.node_type})>"


class WorkflowEdge(Base, TimestampMixin):
    """
    Represents an edge (dependency) between workflow nodes.
    """
    
    __tablename__ = "workflow_edges"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    workflow_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Edge endpoints
    source_node_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Conditional edge (for CONDITION nodes)
    condition_branch: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Data mapping
    data_mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="edges")
    
    def __repr__(self) -> str:
        return f"<WorkflowEdge(source={self.source_node_id}, target={self.target_node_id})>"


class WorkflowExecution(Base, TimestampMixin):
    """
    Represents a single execution of a workflow.
    """
    
    __tablename__ = "workflow_executions"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    workflow_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Multi-tenancy
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    
    # Status
    status: Mapped[WorkflowStatus] = mapped_column(
        String(50),
        default=WorkflowStatus.PENDING,
        nullable=False,
        index=True,
    )
    
    # Input/output
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    output_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Execution context (state of all nodes)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Node states
    node_states: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_node_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    
    # Metadata
    metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="executions")
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def __repr__(self) -> str:
        return f"<WorkflowExecution(id={self.id}, status={self.status})>"
