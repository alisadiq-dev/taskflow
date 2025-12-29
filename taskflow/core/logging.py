"""Structured logging configuration."""

import logging
import sys
from contextvars import ContextVar
from typing import Any, Optional
from uuid import uuid4

import structlog
from structlog.types import EventDict, Processor

# Context variable for correlation ID
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID."""
    return correlation_id_ctx.get()


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID, generating one if not provided."""
    cid = correlation_id or str(uuid4())
    correlation_id_ctx.set(cid)
    return cid


def add_correlation_id(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Processor to add correlation ID to log events."""
    cid = get_correlation_id()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def add_service_info(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Processor to add service info to log events."""
    event_dict["service"] = "taskflow"
    return event_dict


def configure_logging(
    level: str = "INFO",
    format: str = "json",
    service_name: str = "taskflow",
) -> None:
    """
    Configure structured logging for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Output format (json or text)
        service_name: Name of the service for log context
    """
    # Shared processors for both stdlib and structlog
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        add_correlation_id,
        add_service_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    if format == "json":
        # JSON format for production
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Pretty console format for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    # Configure structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure stdlib logging
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Quiet noisy loggers
    for logger_name in ["uvicorn", "uvicorn.access", "httpx", "httpcore"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    # Keep Celery info
    logging.getLogger("celery").setLevel(getattr(logging, level.upper()))


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    Get a bound logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Bound structlog logger
    """
    return structlog.get_logger(name)


class LoggerMixin:
    """Mixin that provides a logger property."""
    
    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        """Get logger for this class."""
        return get_logger(self.__class__.__name__)


# Context manager for adding temporary context
class LogContext:
    """Context manager for temporary log context."""
    
    def __init__(self, **kwargs: Any) -> None:
        self._context = kwargs
        self._token = None
    
    def __enter__(self) -> "LogContext":
        structlog.contextvars.bind_contextvars(**self._context)
        return self
    
    def __exit__(self, *args: Any) -> None:
        structlog.contextvars.unbind_contextvars(*self._context.keys())
