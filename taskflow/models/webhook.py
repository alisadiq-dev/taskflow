"""Webhook models for task completion notifications."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskflow.models.base import Base, TimestampMixin


class WebhookEvent(str, Enum):
    """Events that can trigger webhook notifications."""
    
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_SUCCESS = "task.success"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    TASK_RETRYING = "task.retrying"
    
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_SUCCESS = "workflow.success"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"
    
    SCHEDULE_TRIGGERED = "schedule.triggered"
    SCHEDULE_ERROR = "schedule.error"


class DeliveryStatus(str, Enum):
    """Webhook delivery status."""
    
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class Webhook(Base, TimestampMixin):
    """
    Represents a webhook endpoint for notifications.
    
    Webhooks can subscribe to specific events and will receive
    HTTP POST notifications when those events occur.
    """
    
    __tablename__ = "webhooks"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    # Webhook identification
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Multi-tenancy
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    
    # Endpoint configuration
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    
    # Authentication
    secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Event subscriptions
    events: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    
    # Filtering
    task_filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    
    # Retry configuration
    max_retries: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    retry_delay: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    timeout: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    
    # Statistics
    total_deliveries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_deliveries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_deliveries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Health tracking
    last_delivery_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_success_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Auto-disable after too many failures
    auto_disable_threshold: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    disabled_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Relationships
    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        "WebhookDelivery",
        back_populates="webhook",
        cascade="all, delete-orphan",
    )
    
    @property
    def success_rate(self) -> float:
        """Calculate webhook delivery success rate."""
        if self.total_deliveries == 0:
            return 0.0
        return self.successful_deliveries / self.total_deliveries
    
    @property
    def should_disable(self) -> bool:
        """Check if webhook should be auto-disabled."""
        return self.consecutive_failures >= self.auto_disable_threshold
    
    def __repr__(self) -> str:
        return f"<Webhook(id={self.id}, name={self.name}, active={self.is_active})>"


class WebhookDelivery(Base, TimestampMixin):
    """
    Represents a single webhook delivery attempt.
    """
    
    __tablename__ = "webhook_deliveries"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    webhook_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Event details
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    
    # Related entities
    task_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    workflow_execution_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    
    # Delivery status
    status: Mapped[DeliveryStatus] = mapped_column(
        String(50),
        default=DeliveryStatus.PENDING,
        nullable=False,
        index=True,
    )
    
    # Request details
    request_headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    request_body: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Response details
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timing
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    response_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Retry tracking
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Error details
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    webhook: Mapped["Webhook"] = relationship("Webhook", back_populates="deliveries")
    
    def __repr__(self) -> str:
        return f"<WebhookDelivery(id={self.id}, event={self.event}, status={self.status})>"
