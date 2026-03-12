import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GENERATED_IMAGES_DIR

logger = logging.getLogger(__name__)

_application: Application | None = None
_start_time: float = time.time()

# Conversation state for custom schedule input
_awaiting_schedule: dict[int, int] = {}  # chat_id -> post_id


def _authorized(update: Update) -> bool:
    """Check that the message comes from the authorized chat."""
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        "🌟 *Storylab.io — Bot Attivo*\n\n"
        "Comandi disponibili:\n"
        "/genera N — Genera N post (default 1, max 10)\n"
        "/coda — Post in bozza\n"
        "/programmati — Post schedulati\n"
        "/storico — Ultimi 10 post pubblicati\n"
        "/stato — Stato del server",
        parse_mode="Markdown",
    )


async def cmd_genera(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    count = 1
    if context.args:
        try:
            count = max(1, min(10, int(context.args[0])))
        except ValueError:
            await update.message.reply_text("⚠️ Usa: /genera N (dove N è un numero da 1 a 10)")
            return

    await update.message.reply_text(f"⏳ Genero {count} post, attendere...")

    from db.database import SessionLocal
    from db.models import Post
    from services.content_generator import generate_post_content
    from services.image_generator import generate_image

    db = SessionLocal()
    try:
        for i in range(count):
            try:
                content = generate_post_content()
                post = Post(
                    caption=content["caption"],
                    hashtags=content["hashtags"],
                    image_prompt=content["image_prompt"],
                    status="draft",
                    platforms="both",
                )
                db.add(post)
                db.commit()
                db.refresh(post)

                filename = generate_image(content["image_prompt"], post.id)
                post.image_path = filename
                db.commit()

                await _send_post_preview(update.effective_chat.id, post, context)

            except Exception as exc:
                logger.error("Error generating post %d/%d: %s", i + 1, count, exc)
                await update.message.reply_text(f"❌ Errore generazione post {i + 1}: {exc}")
    finally:
        db.close()


async def cmd_coda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    from db.database import SessionLocal
    from db.models import Post

    db = SessionLocal()
    try:
        drafts = db.query(Post).filter(Post.status == "draft").order_by(Post.created_at.desc()).all()
        if not drafts:
            await update.message.reply_text("📭 Nessun post in coda.")
            return

        await update.message.reply_text(f"📋 *{len(drafts)} post in bozza:*", parse_mode="Markdown")
        for post in drafts:
            await _send_post_preview(update.effective_chat.id, post, context)
    finally:
        db.close()


async def cmd_programmati(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    from db.database import SessionLocal
    from db.models import Post

    db = SessionLocal()
    try:
        scheduled = (
            db.query(Post)
            .filter(Post.status == "scheduled")
            .order_by(Post.scheduled_at)
            .all()
        )
        if not scheduled:
            await update.message.reply_text("📭 Nessun post programmato.")
            return

        lines = ["📅 *Post programmati:*\n"]
        for p in scheduled:
            dt = p.scheduled_at.strftime("%d/%m/%Y %H:%M") if p.scheduled_at else "N/D"
            lines.append(f"• Post #{p.id} — {dt} — {p.platforms}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    finally:
        db.close()


async def cmd_storico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    from db.database import SessionLocal
    from db.models import Post

    db = SessionLocal()
    try:
        published = (
            db.query(Post)
            .filter(Post.status.in_(["published", "failed"]))
            .order_by(Post.published_at.desc())
            .limit(10)
            .all()
        )
        if not published:
            await update.message.reply_text("📭 Nessun post nello storico.")
            return

        lines = ["📜 *Ultimi post:*\n"]
        for p in published:
            dt = p.published_at.strftime("%d/%m/%Y %H:%M") if p.published_at else "N/D"
            icon = "✅" if p.status == "published" else "❌"
            lines.append(f"{icon} #{p.id} — {dt} — {p.platforms}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    finally:
        db.close()


async def cmd_stato(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    from db.database import SessionLocal
    from db.models import Post
    from services.scheduler import get_scheduled_jobs

    uptime_secs = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_secs, 3600)
    minutes, secs = divmod(remainder, 60)

    db = SessionLocal()
    try:
        draft_count = db.query(Post).filter(Post.status == "draft").count()
        scheduled_count = db.query(Post).filter(Post.status == "scheduled").count()
        published_count = db.query(Post).filter(Post.status == "published").count()

        jobs = get_scheduled_jobs()
        next_job = jobs[0]["run_date"] if jobs else "Nessuno"

        await update.message.reply_text(
            f"🖥️ *Stato Storylab.io*\n\n"
            f"⏱ Uptime: {hours}h {minutes}m {secs}s\n"
            f"📝 Bozze: {draft_count}\n"
            f"📅 Programmati: {scheduled_count}\n"
            f"✅ Pubblicati: {published_count}\n"
            f"⏭ Prossimo: {next_job}",
            parse_mode="Markdown",
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Inline keyboard helpers
# ---------------------------------------------------------------------------

def _post_action_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✓ Approva", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton("✎ Rigenera testo", callback_data=f"regen_text_{post_id}"),
        ],
        [
            InlineKeyboardButton("🖼 Rigenera immagine", callback_data=f"regen_image_{post_id}"),
            InlineKeyboardButton("✕ Elimina", callback_data=f"delete_{post_id}"),
        ],
    ])


def _schedule_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ Adesso", callback_data=f"schedule_{post_id}_now"),
            InlineKeyboardButton("🌆 Oggi 18:00", callback_data=f"schedule_{post_id}_today18"),
        ],
        [
            InlineKeyboardButton("🌅 Domani 09:00", callback_data=f"schedule_{post_id}_tomorrow9"),
            InlineKeyboardButton("🕐 Orario custom", callback_data=f"schedule_{post_id}_custom"),
        ],
    ])


async def _send_post_preview(
    chat_id: int,
    post,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Send a post preview (image + caption + action buttons) to the chat."""
    caption_text = f"📝 *Post #{post.id}*\n\n{post.caption}\n\n{post.hashtags}"
    if len(caption_text) > 1024:
        caption_text = caption_text[:1020] + "..."

    keyboard = _post_action_keyboard(post.id)

    if post.image_path:
        image_file = GENERATED_IMAGES_DIR / post.image_path
        if image_file.exists():
            with open(image_file, "rb") as f:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    caption=caption_text,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )
            return

    await context.bot.send_message(
        chat_id=chat_id,
        text=caption_text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ---------------------------------------------------------------------------
# Callback query handler
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    query = update.callback_query
    await query.answer()
    data = query.data

    from db.database import SessionLocal
    from db.models import Post

    if data.startswith("approve_"):
        post_id = int(data.split("_")[1])
        await query.edit_message_reply_markup(reply_markup=_schedule_keyboard(post_id))

    elif data.startswith("schedule_"):
        parts = data.split("_")
        post_id = int(parts[1])
        option = parts[2]

        now = datetime.now(timezone.utc)

        if option == "now":
            scheduled_at = now + timedelta(seconds=10)
        elif option == "today18":
            scheduled_at = now.replace(hour=18, minute=0, second=0, microsecond=0)
            if scheduled_at <= now:
                scheduled_at += timedelta(days=1)
        elif option == "tomorrow9":
            scheduled_at = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        elif option == "custom":
            _awaiting_schedule[update.effective_chat.id] = post_id
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🕐 Post #{post_id}: scrivi data e ora nel formato `DD/MM/YYYY HH:MM`",
                parse_mode="Markdown",
            )
            return
        else:
            return

        _approve_and_schedule(post_id, scheduled_at)
        dt_str = scheduled_at.strftime("%d/%m/%Y %H:%M UTC")
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Post #{post_id} approvato e programmato per {dt_str}",
        )

    elif data.startswith("regen_text_"):
        post_id = int(data.split("_")[2])
        db = SessionLocal()
        try:
            post = db.query(Post).filter(Post.id == post_id).first()
            if not post:
                return

            from services.content_generator import generate_post_content
            content = generate_post_content()
            post.caption = content["caption"]
            post.hashtags = content["hashtags"]
            post.image_prompt = content["image_prompt"]
            db.commit()
            db.refresh(post)

            await query.edit_message_reply_markup(reply_markup=None)
            await _send_post_preview(update.effective_chat.id, post, context)
        finally:
            db.close()

    elif data.startswith("regen_image_"):
        post_id = int(data.split("_")[2])
        db = SessionLocal()
        try:
            post = db.query(Post).filter(Post.id == post_id).first()
            if not post:
                return

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⏳ Rigenero l'immagine per il post #{post_id}...",
            )

            from services.image_generator import generate_image, delete_image
            if post.image_path:
                delete_image(post.image_path)
            filename = generate_image(post.image_prompt, post.id)
            post.image_path = filename
            db.commit()
            db.refresh(post)

            await _send_post_preview(update.effective_chat.id, post, context)
        finally:
            db.close()

    elif data.startswith("delete_"):
        post_id = int(data.split("_")[1])
        db = SessionLocal()
        try:
            post = db.query(Post).filter(Post.id == post_id).first()
            if post:
                if post.image_path:
                    from services.image_generator import delete_image
                    delete_image(post.image_path)
                db.delete(post)
                db.commit()
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🗑️ Post #{post_id} eliminato.",
            )
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Custom schedule text handler
# ---------------------------------------------------------------------------

async def handle_custom_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    chat_id = update.effective_chat.id
    if chat_id not in _awaiting_schedule:
        return

    post_id = _awaiting_schedule.pop(chat_id)
    text = update.message.text.strip()

    try:
        scheduled_at = datetime.strptime(text, "%d/%m/%Y %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        await update.message.reply_text("⚠️ Formato non valido. Usa: DD/MM/YYYY HH:MM")
        _awaiting_schedule[chat_id] = post_id
        return

    _approve_and_schedule(post_id, scheduled_at)
    dt_str = scheduled_at.strftime("%d/%m/%Y %H:%M UTC")
    await update.message.reply_text(f"✅ Post #{post_id} approvato e programmato per {dt_str}")


def _approve_and_schedule(post_id: int, scheduled_at: datetime) -> None:
    """Mark a post as approved, then scheduled, and register the scheduler job."""
    from db.database import SessionLocal
    from db.models import Post
    from services.scheduler import schedule_post

    db = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.status = "scheduled"
            post.scheduled_at = scheduled_at
            db.commit()
            schedule_post(post_id, scheduled_at)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Notifications (called from other modules)
# ---------------------------------------------------------------------------

async def send_notification(text: str) -> None:
    """Send a push message to the authorized user."""
    if _application and _application.bot:
        try:
            await _application.bot.send_message(
                chat_id=int(TELEGRAM_CHAT_ID),
                text=text,
            )
        except Exception as exc:
            logger.error("Failed to send Telegram notification: %s", exc)


async def send_post_preview_notification(post) -> None:
    """Send a post preview as notification (used by API routes)."""
    if _application and _application.bot:
        try:
            caption_text = f"📝 *Post #{post.id}*\n\n{post.caption}\n\n{post.hashtags}"
            if len(caption_text) > 1024:
                caption_text = caption_text[:1020] + "..."

            if post.image_path:
                image_file = GENERATED_IMAGES_DIR / post.image_path
                if image_file.exists():
                    with open(image_file, "rb") as f:
                        await _application.bot.send_photo(
                            chat_id=int(TELEGRAM_CHAT_ID),
                            photo=f,
                            caption=caption_text,
                            parse_mode="Markdown",
                            reply_markup=_post_action_keyboard(post.id),
                        )
                    return

            await _application.bot.send_message(
                chat_id=int(TELEGRAM_CHAT_ID),
                text=caption_text,
                parse_mode="Markdown",
                reply_markup=_post_action_keyboard(post.id),
            )
        except Exception as exc:
            logger.error("Failed to send post preview notification: %s", exc)


# ---------------------------------------------------------------------------
# Bot lifecycle
# ---------------------------------------------------------------------------

async def start_bot() -> None:
    """Initialize and start the Telegram bot with polling."""
    global _application, _start_time

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return

    _start_time = time.time()

    _application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    _application.add_handler(CommandHandler("start", cmd_start))
    _application.add_handler(CommandHandler("genera", cmd_genera))
    _application.add_handler(CommandHandler("coda", cmd_coda))
    _application.add_handler(CommandHandler("programmati", cmd_programmati))
    _application.add_handler(CommandHandler("storico", cmd_storico))
    _application.add_handler(CommandHandler("stato", cmd_stato))
    _application.add_handler(CallbackQueryHandler(handle_callback))
    _application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_schedule)
    )

    await _application.initialize()
    await _application.start()
    await _application.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot started (polling)")


async def stop_bot() -> None:
    """Stop the Telegram bot."""
    global _application
    if _application:
        try:
            await _application.updater.stop()
            await _application.stop()
            await _application.shutdown()
        except Exception as exc:
            logger.warning("Error stopping Telegram bot: %s", exc)
        _application = None
        logger.info("Telegram bot stopped")
