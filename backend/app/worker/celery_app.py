"""Celery application. Task bodies live in app.worker.tasks / services."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "fawtarabridge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # at-least-once: a crashed worker re-delivers (idempotent tasks)
    task_always_eager=settings.celery_eager,
    task_eager_propagates=settings.celery_eager,
    beat_schedule={
        # FR-6.1 weekly digest (interval-based; switch to crontab once the
        # preferred local send time is decided with the pilot customers)
        "weekly-digest": {"task": "app.weekly_digest", "schedule": 7 * 24 * 3600.0},
    },
)


@celery_app.task(name="app.ping")
def ping() -> str:
    return "pong"
