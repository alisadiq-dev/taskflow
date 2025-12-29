"""Webhook service for task completion notifications."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from taskflow.core.config import get_settings
from taskflow.core.exceptions import WebhookNotFoundError, WebhookDeliveryError
from taskflow.core.logging import get_logger, LoggerMixin
from taskflow.database.repository import BaseRepository
from taskflow.models.webhook import (
    Webhook,
    WebhookDelivery,
    WebhookEvent,
    DeliveryStatus,
)

settings = get_settings()
logger = get_logger(__name__)


class WebhookService(LoggerMixin):
    """
    Service for managing webhooks and notifications.
    
    Handles webhook registration, event triggering, and delivery.
    """
    
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.webhook_repo = BaseRepository(Webhook, session)
        self.delivery_repo = BaseRepository(WebhookDelivery, session)
    
    async def create_webhook(
        self,
        name: str,
        url: str,
        events: list[str],
        tenant_id: Optional[str] = None,
        secret: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        task_filters: Optional[dict[str, Any]] = None,
        max_retries: int = 5,
        retry_delay: int = 60,
        timeout: int = 30,
        description: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Webhook:
        """
        Create a new webhook.
        
        Args:
            name: Webhook name
            url: Endpoint URL
            events: List of event types to subscribe to
            tenant_id: Optional tenant ID
            secret: Optional secret for signing payloads
            headers: Optional custom headers
            task_filters: Optional filters for task events
            max_retries: Maximum delivery retries
            retry_delay: Retry delay in seconds
            timeout: Request timeout in seconds
            description: Webhook description
            metadata: Additional metadata
            
        Returns:
            Created webhook
        """
        # Validate events
        valid_events = {e.value for e in WebhookEvent}
        invalid_events = set(events) - valid_events
        if invalid_events:
            raise ValueError(f"Invalid events: {invalid_events}")
        
        webhook = await self.webhook_repo.create(
            id=str(uuid4()),
            name=name,
            description=description,
            tenant_id=tenant_id,
            url=url,
            secret=secret,
            headers=headers or {},
            events=events,
            task_filters=task_filters or {},
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout=timeout,
            metadata=metadata or {},
        )
        
        self.logger.info(
            "Webhook created",
            webhook_id=webhook.id,
            name=name,
            events=events,
        )
        
        return webhook
    
    async def get_webhook(
        self,
        webhook_id: str,
        tenant_id: Optional[str] = None,
    ) -> Webhook:
        """Get webhook by ID."""
        if tenant_id:
            webhook = await self.webhook_repo.get_by(
                id=webhook_id,
                tenant_id=tenant_id,
            )
        else:
            webhook = await self.webhook_repo.get(webhook_id)
        
        if not webhook:
            raise WebhookNotFoundError(webhook_id)
        
        return webhook
    
    async def list_webhooks(
        self,
        tenant_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Webhook]:
        """List webhooks with filtering."""
        filters = {}
        
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if is_active is not None:
            filters["is_active"] = is_active
        
        return await self.webhook_repo.get_all(
            skip=skip,
            limit=limit,
            order_by="created_at",
            descending=True,
            **filters,
        )
    
    async def update_webhook(
        self,
        webhook_id: str,
        tenant_id: Optional[str] = None,
        **updates: Any,
    ) -> Webhook:
        """Update a webhook."""
        webhook = await self.get_webhook(webhook_id, tenant_id)
        return await self.webhook_repo.update(webhook_id, **updates)
    
    async def delete_webhook(
        self,
        webhook_id: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Delete a webhook."""
        webhook = await self.get_webhook(webhook_id, tenant_id)
        return await self.webhook_repo.delete(webhook_id)
    
    async def trigger_event(
        self,
        event: str,
        task_id: Optional[str] = None,
        workflow_execution_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> list[WebhookDelivery]:
        """
        Trigger an event and send to all subscribed webhooks.
        
        Args:
            event: Event type
            task_id: Optional related task ID
            workflow_execution_id: Optional related workflow execution ID
            tenant_id: Optional tenant ID for filtering webhooks
            payload: Event payload
            
        Returns:
            List of webhook delivery records
        """
        # Find subscribed webhooks
        query = select(Webhook).where(
            Webhook.is_active == True,
            Webhook.events.contains([event]),
        )
        
        if tenant_id:
            query = query.where(Webhook.tenant_id == tenant_id)
        
        result = await self.session.execute(query)
        webhooks = result.scalars().all()
        
        if not webhooks:
            self.logger.debug(
                "No webhooks subscribed to event",
                event=event,
                tenant_id=tenant_id,
            )
            return []
        
        deliveries = []
        
        # Build event payload
        event_payload = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "workflow_execution_id": workflow_execution_id,
            "data": payload or {},
        }
        
        for webhook in webhooks:
            # Check task filters if applicable
            if task_id and webhook.task_filters:
                if not self._matches_filters(payload, webhook.task_filters):
                    continue
            
            # Create delivery record
            delivery = await self.delivery_repo.create(
                id=str(uuid4()),
                webhook_id=webhook.id,
                event=event,
                payload=event_payload,
                task_id=task_id,
                workflow_execution_id=workflow_execution_id,
                status=DeliveryStatus.PENDING,
            )
            
            deliveries.append(delivery)
            
            # Queue delivery task
            from taskflow.worker.tasks import send_webhook
            send_webhook.delay(
                webhook_id=webhook.id,
                delivery_id=delivery.id,
                url=webhook.url,
                payload=event_payload,
                headers=webhook.headers,
                secret=webhook.secret,
            )
        
        self.logger.info(
            "Event triggered",
            event=event,
            webhooks_count=len(deliveries),
        )
        
        return deliveries
    
    def _matches_filters(
        self,
        payload: Optional[dict[str, Any]],
        filters: dict[str, Any],
    ) -> bool:
        """Check if payload matches webhook filters."""
        if not payload:
            return False
        
        for key, value in filters.items():
            if key not in payload:
                return False
            
            if isinstance(value, list):
                if payload[key] not in value:
                    return False
            elif payload[key] != value:
                return False
        
        return True
    
    async def get_delivery(
        self,
        delivery_id: str,
        webhook_id: Optional[str] = None,
    ) -> WebhookDelivery:
        """Get delivery by ID."""
        if webhook_id:
            delivery = await self.delivery_repo.get_by(
                id=delivery_id,
                webhook_id=webhook_id,
            )
        else:
            delivery = await self.delivery_repo.get(delivery_id)
        
        if not delivery:
            raise WebhookDeliveryError(
                webhook_id or "unknown",
                reason="Delivery not found",
            )
        
        return delivery
    
    async def list_deliveries(
        self,
        webhook_id: Optional[str] = None,
        status: Optional[DeliveryStatus] = None,
        event: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WebhookDelivery]:
        """List deliveries with filtering."""
        filters = {}
        
        if webhook_id:
            filters["webhook_id"] = webhook_id
        if status:
            filters["status"] = status
        if event:
            filters["event"] = event
        
        return await self.delivery_repo.get_all(
            skip=skip,
            limit=limit,
            order_by="created_at",
            descending=True,
            **filters,
        )
    
    async def retry_delivery(
        self,
        delivery_id: str,
        webhook_id: Optional[str] = None,
    ) -> WebhookDelivery:
        """Retry a failed delivery."""
        delivery = await self.get_delivery(delivery_id, webhook_id)
        webhook = await self.get_webhook(delivery.webhook_id)
        
        if delivery.status != DeliveryStatus.FAILED:
            raise WebhookDeliveryError(
                delivery.webhook_id,
                reason="Can only retry failed deliveries",
            )
        
        # Reset delivery status
        await self.delivery_repo.update(
            delivery_id,
            status=DeliveryStatus.PENDING,
            error_message=None,
            attempt=delivery.attempt + 1,
        )
        
        # Queue retry
        from taskflow.worker.tasks import send_webhook
        send_webhook.delay(
            webhook_id=webhook.id,
            delivery_id=delivery.id,
            url=webhook.url,
            payload=delivery.payload,
            headers=webhook.headers,
            secret=webhook.secret,
        )
        
        return await self.get_delivery(delivery_id)
    
    async def get_webhook_stats(
        self,
        webhook_id: str,
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get statistics for a webhook."""
        webhook = await self.get_webhook(webhook_id, tenant_id)
        
        # Count deliveries by status
        status_counts = {}
        for status in DeliveryStatus:
            count = await self.delivery_repo.count(
                webhook_id=webhook_id,
                status=status,
            )
            status_counts[status.value] = count
        
        return {
            "webhook_id": webhook_id,
            "total_deliveries": webhook.total_deliveries,
            "successful_deliveries": webhook.successful_deliveries,
            "failed_deliveries": webhook.failed_deliveries,
            "success_rate": webhook.success_rate,
            "consecutive_failures": webhook.consecutive_failures,
            "last_delivery_at": webhook.last_delivery_at.isoformat() if webhook.last_delivery_at else None,
            "last_success_at": webhook.last_success_at.isoformat() if webhook.last_success_at else None,
            "by_status": status_counts,
        }
    
    def generate_signature(
        self,
        payload: str,
        secret: str,
    ) -> str:
        """Generate HMAC signature for payload."""
        signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={signature}"
    
    def verify_signature(
        self,
        payload: str,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify HMAC signature."""
        expected = self.generate_signature(payload, secret)
        return hmac.compare_digest(expected, signature)
