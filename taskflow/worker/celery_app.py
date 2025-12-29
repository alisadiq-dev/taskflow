"""Celery application configuration."""

from celery import Celery
from kombu import Exchange, Queue

from taskflow.core.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "taskflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.scheduler_timezone,
    enable_utc=True,
    
    # Task execution
    task_acks_late=settings.celery_task_acks_late,
    task_reject_on_worker_lost=settings.celery_task_reject_on_worker_lost,
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_always_eager=settings.celery_task_always_eager,
    
    # Worker settings
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    worker_concurrency=4,
    
    # Result backend
    result_expires=3600,  # Results expire after 1 hour
    result_extended=True,  # Store additional task metadata
    
    # Routing
    task_routes={
        "taskflow.worker.tasks.execute_task": {"queue": "default"},
        "taskflow.worker.tasks.process_dead_letter": {"queue": "dead_letter"},
        "taskflow.worker.tasks.send_webhook": {"queue": "webhooks"},
    },
    
    # Beat scheduler (for periodic tasks)
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename="celerybeat-schedule",
)

# Define exchanges
default_exchange = Exchange("default", type="direct")
priority_exchange = Exchange("priority", type="direct")
dlq_exchange = Exchange("dlq", type="direct")

# Define queues with priorities
celery_app.conf.task_queues = (
    # Priority queues
    Queue(
        settings.queue_critical,
        exchange=priority_exchange,
        routing_key="critical",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        settings.queue_high,
        exchange=priority_exchange,
        routing_key="high",
        queue_arguments={"x-max-priority": 7},
    ),
    Queue(
        settings.queue_default,
        exchange=default_exchange,
        routing_key="default",
        queue_arguments={"x-max-priority": 5},
    ),
    Queue(
        settings.queue_low,
        exchange=priority_exchange,
        routing_key="low",
        queue_arguments={"x-max-priority": 3},
    ),
    # Dead letter queue
    Queue(
        settings.queue_dead_letter,
        exchange=dlq_exchange,
        routing_key="dead_letter",
    ),
    # Webhook queue
    Queue(
        "webhooks",
        exchange=default_exchange,
        routing_key="webhooks",
    ),
)

# Default queue
celery_app.conf.task_default_queue = settings.queue_default
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "default"


def get_queue_for_priority(priority: str) -> str:
    """Map priority to queue name."""
    priority_queue_map = {
        "critical": settings.queue_critical,
        "high": settings.queue_high,
        "normal": settings.queue_default,
        "low": settings.queue_low,
    }
    return priority_queue_map.get(priority, settings.queue_default)


def get_priority_value(priority: str) -> int:
    """Map priority to numeric value for Celery."""
    priority_values = {
        "critical": 10,
        "high": 7,
        "normal": 5,
        "low": 3,
    }
    return priority_values.get(priority, 5)
