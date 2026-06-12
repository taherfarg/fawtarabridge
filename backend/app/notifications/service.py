"""Notification interface (FR-6): WhatsApp + email fallback, console stubs.

Every send is recorded in the `notifications` table so the demo/tests/UI can see
what would have gone out. Owner rejection alerts can never be disabled (FR-6.3)
— there are no preferences yet, so everything reaches all OWNER members.
"""

import logging
import uuid
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.i18n import t
from app.models import TenantMembership, User
from app.models.billing import NotificationRecord
from app.models.enums import Role

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    name: str

    def send(self, recipient: str, message: str) -> None: ...


class ConsoleWhatsAppChannel:
    name = "whatsapp"

    def send(self, recipient: str, message: str) -> None:
        logger.info("whatsapp-stub -> %s: %s", recipient, message)


class ConsoleEmailChannel:
    name = "email"

    def send(self, recipient: str, message: str) -> None:
        logger.info("email-stub -> %s: %s", recipient, message)


_channels: list[NotificationChannel] = [ConsoleWhatsAppChannel(), ConsoleEmailChannel()]


def render(template: str, params: dict[str, Any]) -> str:
    """Bilingual body: Arabic first (product default), English after."""
    ar = t(f"notifications.{template}", "ar", **params) or template
    en = t(f"notifications.{template}", "en", **params) or template
    return f"{ar}\n{en}"


def notify_owners(
    db: Session, tenant_id: uuid.UUID, *, template: str, params: dict[str, Any]
) -> int:
    """Send to every OWNER via WhatsApp + email fallback; log each delivery."""
    owners = (
        db.execute(
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(TenantMembership.tenant_id == tenant_id, TenantMembership.role == Role.OWNER)
        )
        .scalars()
        .all()
    )

    message = render(template, params)
    sent = 0
    for owner in owners:
        for channel in _channels:
            recipient = owner.phone if channel.name == "whatsapp" else owner.email
            channel.send(recipient, message)
            db.add(
                NotificationRecord(
                    tenant_id=tenant_id,
                    user_id=owner.id,
                    channel=channel.name,
                    recipient=recipient,
                    template=template,
                    params=params,
                )
            )
            sent += 1
    return sent
