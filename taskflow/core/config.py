"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Any, Optional

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables with
    the TASKFLOW_ prefix.
    """
    
    model_config = SettingsConfigDict(
        env_prefix="TASKFLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Application
    app_name: str = "TaskFlow"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    
    # API
    api_prefix: str = "/api/v1"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    openapi_url: str = "/openapi.json"
    
    # Security
    secret_key: str = Field(default="change-me-in-production-please!")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours
    allowed_hosts: list[str] = ["*"]
    cors_origins: list[str] = ["*"]
    
    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://taskflow:taskflow@localhost:5432/taskflow"
    )
    database_pool_size: int = 20
    database_pool_overflow: int = 10
    database_pool_timeout: int = 30
    database_echo: bool = False
    
    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_pool_size: int = 10
    redis_decode_responses: bool = True
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_always_eager: bool = False  # Set True for testing
    celery_task_acks_late: bool = True
    celery_task_reject_on_worker_lost: bool = True
    celery_worker_prefetch_multiplier: int = 1
    celery_task_time_limit: int = 3600  # 1 hour
    celery_task_soft_time_limit: int = 3300  # 55 minutes
    
    # Task Queues
    queue_critical: str = "critical"
    queue_high: str = "high"
    queue_default: str = "default"
    queue_low: str = "low"
    queue_dead_letter: str = "dead_letter"
    
    # Scheduler
    scheduler_enabled: bool = True
    scheduler_job_store: str = "redis://localhost:6379/3"
    scheduler_timezone: str = "UTC"
    
    # WebSocket
    websocket_path: str = "/ws"
    websocket_ping_interval: int = 30
    websocket_ping_timeout: int = 10
    
    # Webhooks
    webhook_timeout: int = 30
    webhook_max_retries: int = 5
    webhook_retry_delay: int = 60
    
    # Monitoring
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    health_path: str = "/health"
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text
    log_correlation_id_header: str = "X-Correlation-ID"
    
    # Multi-tenancy
    multi_tenant_enabled: bool = False
    tenant_header: str = "X-Tenant-ID"
    
    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> Any:
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v
    
    @property
    def sync_database_url(self) -> str:
        """Get synchronous database URL for Alembic."""
        url = str(self.database_url)
        return url.replace("postgresql+asyncpg://", "postgresql://")
    
    @property
    def celery_queues(self) -> list[str]:
        """Get list of all Celery queues."""
        return [
            self.queue_critical,
            self.queue_high,
            self.queue_default,
            self.queue_low,
            self.queue_dead_letter,
        ]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
