from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Text

from db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    caption = Column(Text, nullable=False)
    hashtags = Column(Text, nullable=False, default="")
    image_prompt = Column(Text, nullable=False, default="")
    image_path = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="draft")
    platforms = Column(String(20), nullable=False, default="both")
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    fb_post_id = Column(String(200), nullable=True)
    ig_post_id = Column(String(200), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "image_prompt": self.image_prompt,
            "image_path": self.image_path,
            "status": self.status,
            "platforms": self.platforms,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "fb_post_id": self.fb_post_id,
            "ig_post_id": self.ig_post_id,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
