import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import APP_HOST, APP_PORT, GENERATED_IMAGES_DIR, STATIC_DIR

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("storylab")


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    from db.database import init_db
    init_db()
    logger.info("Database initialized")

    from services.scheduler import start_scheduler
    start_scheduler()
    logger.info("Scheduler started")

    from services.telegram_bot import start_bot
    asyncio.create_task(start_bot())
    logger.info("Telegram bot starting...")

    yield

    # --- shutdown ---
    from services.scheduler import stop_scheduler
    stop_scheduler()

    from services.telegram_bot import stop_bot
    await stop_bot()

    logger.info("Storylab.io shut down gracefully")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Storylab.io",
    description="AI Social Content Manager — Crescita personale & Spiritualità",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount generated images
app.mount("/images", StaticFiles(directory=str(GENERATED_IMAGES_DIR)), name="images")

# API routes
from api.routes_posts import router as posts_router
from api.routes_schedule import router as schedule_router

app.include_router(posts_router)
app.include_router(schedule_router)

# Serve frontend (must be last so it doesn't shadow API routes)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=False,
        log_level="info",
    )
