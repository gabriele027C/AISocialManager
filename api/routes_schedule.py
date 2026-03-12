import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Post
from services.scheduler import get_scheduled_jobs, remove_scheduled_post

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("")
def list_scheduled(db: Session = Depends(get_db)):
    """Return all scheduled posts ordered by scheduled_at."""
    posts = (
        db.query(Post)
        .filter(Post.status == "scheduled")
        .order_by(Post.scheduled_at)
        .all()
    )
    jobs = get_scheduled_jobs()
    return {
        "posts": [p.to_dict() for p in posts],
        "jobs": jobs,
    }


@router.delete("/{post_id}")
def unschedule_post(post_id: int, db: Session = Depends(get_db)):
    """Remove scheduling from a post, reverting it to approved status."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status != "scheduled":
        raise HTTPException(status_code=400, detail=f"Post is '{post.status}', not scheduled")

    remove_scheduled_post(post_id)
    post.status = "approved"
    post.scheduled_at = None
    db.commit()
    return post.to_dict()
