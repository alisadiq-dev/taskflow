"""Schedule service for managing recurring tasks."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.redis import RedisJobStore
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from taskflow.core.config import get_settings
from taskflow.core.exceptions import ScheduleNotFoundError, ScheduleValidationError
from taskflow.core.logging import get_logger, LoggerMixin
from taskflow.database.repository import BaseRepository
from taskflow.models.schedule import Schedule, ScheduleType
from taskflow.models.task import TaskPriority

settings = get_settings()
logger = get_logger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler."""
    global _scheduler
    if _scheduler is None:
        # Configure job stores
        jobstores = {
            "default": RedisJobStore(
                host=settings.redis_url.host,
                port=settings.redis_url.port or 6379,
                db=3,
            )
        }
        
        _scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=settings.scheduler_timezone,
        )
    
    return _scheduler


async def start_scheduler() -> None:
    """Start the scheduler."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


async def stop_scheduler() -> None:
    """Stop the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


class ScheduleService(LoggerMixin):
    """
    Service for managing scheduled/recurring tasks.
    
    Uses APScheduler for cron-like scheduling with Redis persistence.
    """
    
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = BaseRepository(Schedule, session)
        self.scheduler = get_scheduler()
    
    async def create_schedule(
        self,
        name: str,
        task_type: str,
        task_name: str,
        schedule_type: ScheduleType,
        task_payload: Optional[dict[str, Any]] = None,
        task_priority: TaskPriority = TaskPriority.NORMAL,
        task_queue: str = "default",
        tenant_id: Optional[str] = None,
        cron_expression: Optional[str] = None,
        interval_seconds: Optional[int] = None,
        run_date: Optional[datetime] = None,
        timezone_str: str = "UTC",
        max_runs: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Schedule:
        """
        Create a new schedule.
        
        Args:
            name: Unique schedule name
            task_type: Type of task to create
            task_name: Name for created tasks
            schedule_type: Type of schedule (cron, interval, date)
            task_payload: Payload for created tasks
            task_priority: Priority for created tasks
            task_queue: Queue for created tasks
            tenant_id: Optional tenant ID
            cron_expression: Cron expression (for CRON type)
            interval_seconds: Interval in seconds (for INTERVAL type)
            run_date: Run date (for DATE type)
            timezone_str: Timezone for schedule
            max_runs: Maximum number of runs
            expires_at: Expiration datetime
            description: Schedule description
            tags: Tags for filtering
            metadata: Additional metadata
            
        Returns:
            Created schedule
            
        Raises:
            ScheduleValidationError: If schedule configuration is invalid
        """
        # Validate schedule configuration
        self._validate_schedule(
            schedule_type,
            cron_expression,
            interval_seconds,
            run_date,
        )
        
        # Calculate next run time
        next_run = self._calculate_next_run(
            schedule_type,
            cron_expression,
            interval_seconds,
            run_date,
            timezone_str,
        )
        
        # Create schedule record
        schedule = await self.repository.create(
            id=str(uuid4()),
            name=name,
            description=description,
            tenant_id=tenant_id,
            task_type=task_type,
            task_name=task_name,
            task_payload=task_payload or {},
            task_priority=task_priority,
            task_queue=task_queue,
            schedule_type=schedule_type,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            run_date=run_date,
            timezone=timezone_str,
            next_run_at=next_run,
            max_runs=max_runs,
            expires_at=expires_at,
            tags=tags or [],
            metadata=metadata or {},
        )
        
        # Create APScheduler job
        await self._create_apscheduler_job(schedule)
        
        self.logger.info(
            "Schedule created",
            schedule_id=schedule.id,
            name=name,
            type=schedule_type.value,
        )
        
        return schedule
    
    def _validate_schedule(
        self,
        schedule_type: ScheduleType,
        cron_expression: Optional[str],
        interval_seconds: Optional[int],
        run_date: Optional[datetime],
    ) -> None:
        """Validate schedule configuration."""
        if schedule_type == ScheduleType.CRON:
            if not cron_expression:
                raise ScheduleValidationError(
                    "Cron expression required for CRON schedule type"
                )
            # Validate cron expression
            try:
                CronTrigger.from_crontab(cron_expression)
            except ValueError as e:
                raise ScheduleValidationError(f"Invalid cron expression: {e}")
        
        elif schedule_type == ScheduleType.INTERVAL:
            if not interval_seconds or interval_seconds < 1:
                raise ScheduleValidationError(
                    "Interval seconds required and must be positive"
                )
        
        elif schedule_type == ScheduleType.DATE:
            if not run_date:
                raise ScheduleValidationError(
                    "Run date required for DATE schedule type"
                )
            if run_date <= datetime.now(timezone.utc):
                raise ScheduleValidationError("Run date must be in the future")
    
    def _calculate_next_run(
        self,
        schedule_type: ScheduleType,
        cron_expression: Optional[str],
        interval_seconds: Optional[int],
        run_date: Optional[datetime],
        timezone_str: str,
    ) -> Optional[datetime]:
        """Calculate next run time."""
        import pytz
        
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        
        if schedule_type == ScheduleType.CRON:
            trigger = CronTrigger.from_crontab(cron_expression, timezone=tz)
            return trigger.get_next_fire_time(None, now)
        
        elif schedule_type == ScheduleType.INTERVAL:
            return now + timedelta(seconds=interval_seconds)
        
        elif schedule_type == ScheduleType.DATE:
            return run_date
        
        return None
    
    async def _create_apscheduler_job(self, schedule: Schedule) -> None:
        """Create APScheduler job for schedule."""
        job_id = f"schedule-{schedule.id}"
        
        # Create trigger based on type
        if schedule.schedule_type == ScheduleType.CRON:
            trigger = CronTrigger.from_crontab(
                schedule.cron_expression,
                timezone=schedule.timezone,
            )
        elif schedule.schedule_type == ScheduleType.INTERVAL:
            trigger = IntervalTrigger(
                seconds=schedule.interval_seconds,
                timezone=schedule.timezone,
            )
        elif schedule.schedule_type == ScheduleType.DATE:
            trigger = DateTrigger(
                run_date=schedule.run_date,
                timezone=schedule.timezone,
            )
        else:
            self.logger.warning(
                "Unsupported schedule type",
                schedule_id=schedule.id,
                type=schedule.schedule_type.value,
            )
            return
        
        # Add job
        self.scheduler.add_job(
            self._execute_scheduled_task,
            trigger=trigger,
            id=job_id,
            args=[schedule.id],
            replace_existing=True,
            max_instances=1,
        )
        
        # Update schedule with job ID
        await self.repository.update(
            schedule.id,
            apscheduler_job_id=job_id,
        )
    
    async def _execute_scheduled_task(self, schedule_id: str) -> None:
        """Execute a scheduled task."""
        from taskflow.database.session import get_session_context
        from taskflow.services.task_service import TaskService
        
        async with get_session_context() as session:
            schedule = await session.get(Schedule, schedule_id)
            if not schedule or not schedule.should_run:
                return
            
            try:
                # Create task
                task_service = TaskService(session)
                await task_service.create_task(
                    name=schedule.task_name,
                    task_type=schedule.task_type,
                    payload=schedule.task_payload,
                    priority=schedule.task_priority,
                    tenant_id=schedule.tenant_id,
                    metadata={"schedule_id": schedule.id},
                )
                
                # Update schedule stats
                schedule.last_run_at = datetime.now(timezone.utc)
                schedule.run_count += 1
                schedule.consecutive_failures = 0
                
                # Calculate next run
                schedule.next_run_at = self._calculate_next_run(
                    schedule.schedule_type,
                    schedule.cron_expression,
                    schedule.interval_seconds,
                    schedule.run_date,
                    schedule.timezone,
                )
                
                # Check if expired
                if schedule.is_expired:
                    schedule.is_active = False
                
                await session.commit()
                
                self.logger.info(
                    "Scheduled task executed",
                    schedule_id=schedule_id,
                    run_count=schedule.run_count,
                )
                
            except Exception as e:
                schedule.consecutive_failures += 1
                schedule.last_error = str(e)
                
                if schedule.consecutive_failures >= schedule.max_consecutive_failures:
                    schedule.is_active = False
                    self.logger.error(
                        "Schedule disabled due to consecutive failures",
                        schedule_id=schedule_id,
                        failures=schedule.consecutive_failures,
                    )
                
                await session.commit()
                raise
    
    async def get_schedule(
        self,
        schedule_id: str,
        tenant_id: Optional[str] = None,
    ) -> Schedule:
        """Get schedule by ID."""
        if tenant_id:
            schedule = await self.repository.get_by(
                id=schedule_id,
                tenant_id=tenant_id,
            )
        else:
            schedule = await self.repository.get(schedule_id)
        
        if not schedule:
            raise ScheduleNotFoundError(schedule_id)
        
        return schedule
    
    async def list_schedules(
        self,
        tenant_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        schedule_type: Optional[ScheduleType] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Schedule]:
        """List schedules with filtering."""
        filters = {}
        
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if is_active is not None:
            filters["is_active"] = is_active
        if schedule_type:
            filters["schedule_type"] = schedule_type
        
        return await self.repository.get_all(
            skip=skip,
            limit=limit,
            order_by="created_at",
            descending=True,
            **filters,
        )
    
    async def pause_schedule(
        self,
        schedule_id: str,
        tenant_id: Optional[str] = None,
    ) -> Schedule:
        """Pause a schedule."""
        schedule = await self.get_schedule(schedule_id, tenant_id)
        
        if schedule.apscheduler_job_id:
            self.scheduler.pause_job(schedule.apscheduler_job_id)
        
        return await self.repository.update(schedule_id, is_paused=True)
    
    async def resume_schedule(
        self,
        schedule_id: str,
        tenant_id: Optional[str] = None,
    ) -> Schedule:
        """Resume a paused schedule."""
        schedule = await self.get_schedule(schedule_id, tenant_id)
        
        if schedule.apscheduler_job_id:
            self.scheduler.resume_job(schedule.apscheduler_job_id)
        
        return await self.repository.update(schedule_id, is_paused=False)
    
    async def delete_schedule(
        self,
        schedule_id: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Delete a schedule."""
        schedule = await self.get_schedule(schedule_id, tenant_id)
        
        # Remove APScheduler job
        if schedule.apscheduler_job_id:
            try:
                self.scheduler.remove_job(schedule.apscheduler_job_id)
            except Exception:
                pass
        
        return await self.repository.delete(schedule_id)
    
    async def trigger_schedule(
        self,
        schedule_id: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Manually trigger a schedule."""
        schedule = await self.get_schedule(schedule_id, tenant_id)
        
        if schedule.apscheduler_job_id:
            # Run job immediately
            job = self.scheduler.get_job(schedule.apscheduler_job_id)
            if job:
                await self._execute_scheduled_task(schedule_id)
        else:
            # Create job and run
            await self._execute_scheduled_task(schedule_id)


# Import timedelta at module level
from datetime import timedelta
