import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Post

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/posts", tags=["posts"])


@router.get("/themes")
def list_themes():
    """Return available themes and the currently active one."""
    from services.content_generator import get_available_themes, get_current_theme
    return {"current": get_current_theme(), "available": get_available_themes()}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    count: int = 1
    platforms: str = "both"
    theme: str | None = None


class ScheduleRequest(BaseModel):
    scheduled_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate")
def generate_posts(req: GenerateRequest, db: Session = Depends(get_db)):
    """Generate N posts (text + image) and save them as drafts."""
    from services.content_generator import generate_post_content
    from services.image_generator import generate_image

    count = max(1, min(10, req.count))
    platforms = req.platforms if req.platforms in ("instagram", "facebook", "both") else "both"

    created: list[dict] = []

    for i in range(count):
        try:
            content = generate_post_content(theme_id=req.theme)
            post = Post(
                caption=content["caption"],
                hashtags=content["hashtags"],
                image_prompt=content["image_prompt"],
                status="draft",
                platforms=platforms,
            )
            db.add(post)
            db.commit()
            db.refresh(post)

            filename = generate_image(content["image_prompt"], post.id)
            post.image_path = filename
            db.commit()
            db.refresh(post)

            created.append(post.to_dict())
            logger.info("Generated post #%d (%d/%d)", post.id, i + 1, count)

        except Exception as exc:
            logger.error("Failed generating post %d/%d: %s", i + 1, count, exc)
            db.rollback()
            created.append({"error": str(exc), "index": i + 1})

    return {"posts": created, "generated": len([p for p in created if "error" not in p])}


@router.get("")
def list_posts(status: str | None = Query(None), db: Session = Depends(get_db)):
    """List all posts, optionally filtered by status."""
    query = db.query(Post)
    if status:
        query = query.filter(Post.status == status)
    posts = query.order_by(Post.created_at.desc()).all()
    return {"posts": [p.to_dict() for p in posts]}


@router.get("/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post.to_dict()


@router.put("/{post_id}/approve")
def approve_post(post_id: int, db: Session = Depends(get_db)):
    """Move a draft post to approved status."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status != "draft":
        raise HTTPException(status_code=400, detail=f"Post is '{post.status}', expected 'draft'")

    post.status = "approved"
    db.commit()
    return post.to_dict()


@router.put("/{post_id}/schedule")
def schedule_post_endpoint(post_id: int, req: ScheduleRequest, db: Session = Depends(get_db)):
    """Schedule an approved post for a specific date/time."""
    from services.scheduler import schedule_post

    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status not in ("draft", "approved"):
        raise HTTPException(status_code=400, detail=f"Post is '{post.status}', cannot schedule")

    try:
        scheduled_at = datetime.fromisoformat(req.scheduled_at)
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format. Use ISO 8601.")

    post.status = "scheduled"
    post.scheduled_at = scheduled_at
    db.commit()

    schedule_post(post_id, scheduled_at)
    return post.to_dict()


@router.post("/{post_id}/regenerate-text")
def regenerate_text(post_id: int, db: Session = Depends(get_db)):
    """Regenerate only the text of a post, keeping the image."""
    from services.content_generator import generate_post_content

    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    content = generate_post_content()
    post.caption = content["caption"]
    post.hashtags = content["hashtags"]
    post.image_prompt = content["image_prompt"]
    db.commit()
    db.refresh(post)
    return post.to_dict()


@router.post("/{post_id}/regenerate-image")
def regenerate_image(post_id: int, db: Session = Depends(get_db)):
    """Regenerate only the image of a post, keeping the text."""
    from services.image_generator import generate_image, delete_image

    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.image_path:
        delete_image(post.image_path)

    filename = generate_image(post.image_prompt, post.id)
    post.image_path = filename
    db.commit()
    db.refresh(post)
    return post.to_dict()


@router.post("/{post_id}/publish-now")
async def publish_now(post_id: int, db: Session = Depends(get_db)):
    """Approve and immediately publish a post."""
    from services.meta_publisher import publish_post

    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status in ("published", "scheduled"):
        raise HTTPException(status_code=400, detail=f"Post is already '{post.status}'")

    post.status = "approved"
    db.commit()

    await publish_post(post, db)

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
    except Exception:
        pass

    db.refresh(post)
    return post.to_dict()


@router.delete("/{post_id}")
def delete_post(post_id: int, db: Session = Depends(get_db)):
    """Delete a post and its image from disk."""
    from services.image_generator import delete_image
    from services.scheduler import remove_scheduled_post

    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.image_path:
        delete_image(post.image_path)

    if post.status == "scheduled":
        remove_scheduled_post(post_id)

    db.delete(post)
    db.commit()
    return {"detail": f"Post {post_id} deleted"}
