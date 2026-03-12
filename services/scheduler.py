import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from config import DATABASE_URL

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores = {"default": SQLAlchemyJobStore(url=DATABASE_URL)}
        _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
    return _scheduler


def start_scheduler() -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started")


def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


async def _execute_publish(post_id: int) -> None:
    """Job callback: publish a scheduled post and send Telegram notification."""
    from db.database import SessionLocal
    from db.models import Post
    from services.meta_publisher import publish_post

    db = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if not post:
            logger.error("Scheduled publish: post %d not found", post_id)
            return
        if post.status != "scheduled":
            logger.warning("Post %d is not scheduled (status=%s), skipping", post_id, post.status)
            return

        await publish_post(post, db)

        # Send Telegram notification
        try:
            from services.telegram_bot import send_notification
            if post.status == "published":
                platforms = []
                if post.fb_post_id:
                    platforms.append("Facebook")
                if post.ig_post_id:
                    platforms.append("Instagram")
                await send_notification(
                    f"✅ Post #{post.id} pubblicato con successo su {', '.join(platforms)}!"
                )
            else:
                await send_notification(
                    f"❌ Errore pubblicazione post #{post.id}: {post.error_message}"
                )
        except Exception as notify_exc:
            logger.warning("Failed to send Telegram notification: %s", notify_exc)

    finally:
        db.close()


def schedule_post(post_id: int, scheduled_at: datetime) -> None:
    """Add a job to publish a post at the specified time."""
    scheduler = get_scheduler()
    job_id = f"publish_post_{post_id}"

    scheduler.add_job(
        _execute_publish,
        trigger="date",
        run_date=scheduled_at,
        args=[post_id],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info("Scheduled post %d for %s (job_id=%s)", post_id, scheduled_at, job_id)


def remove_scheduled_post(post_id: int) -> None:
    """Remove a scheduled job for a post."""
    scheduler = get_scheduler()
    job_id = f"publish_post_{post_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info("Removed scheduled job for post %d", post_id)
    except Exception:
        logger.warning("Job %s not found, nothing to remove", job_id)


def get_scheduled_jobs() -> list[dict]:
    """Return a list of currently scheduled jobs."""
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "job_id": job.id,
            "run_date": str(job.next_run_time),
            "post_id": job.args[0] if job.args else None,
        })
    return jobs
