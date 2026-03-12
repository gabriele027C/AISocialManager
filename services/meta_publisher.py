import logging

import httpx

from config import (
    META_ACCESS_TOKEN,
    FACEBOOK_PAGE_ID,
    INSTAGRAM_BUSINESS_ACCOUNT_ID,
    BASE_URL,
    GENERATED_IMAGES_DIR,
)

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _raise_meta_error(resp: httpx.Response, platform: str) -> None:
    """Log the full Meta API error body and raise."""
    try:
        body = resp.json()
        error_info = body.get("error", body)
        msg = error_info.get("message", resp.text) if isinstance(error_info, dict) else resp.text
    except Exception:
        msg = resp.text
    logger.error("%s API %d: %s", platform, resp.status_code, msg)
    resp.raise_for_status()


async def _upload_to_catbox(file_path, filename: str) -> str:
    """Upload via catbox.moe (free, no API key, up to 200 MB)."""
    async with httpx.AsyncClient(timeout=90) as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (filename, f, "image/png")},
            )
        resp.raise_for_status()
        url = resp.text.strip()
        if not url.startswith("http"):
            raise RuntimeError(f"Unexpected catbox response: {url}")
    logger.info("Image uploaded to Catbox: %s", url)
    return url


async def _upload_via_telegram(file_path, filename: str) -> str:
    """Upload via the Telegram Bot API (sendDocument + getFile)."""
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

    tg_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    async with httpx.AsyncClient(timeout=60) as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                f"{tg_api}/sendDocument",
                data={"chat_id": TELEGRAM_CHAT_ID, "disable_notification": "true"},
                files={"document": (filename, f, "image/png")},
            )
        resp.raise_for_status()
        file_id = resp.json()["result"]["document"]["file_id"]

        resp = await client.get(f"{tg_api}/getFile", params={"file_id": file_id})
        resp.raise_for_status()
        tg_path = resp.json()["result"]["file_path"]

    url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{tg_path}"
    logger.info("Image uploaded via Telegram Bot: %s", url)
    return url


async def _upload_for_public_url(image_filename: str) -> str:
    """Get a publicly accessible URL for the image (for Instagram).

    Tries Catbox first, then falls back to the Telegram Bot API.
    """
    file_path = GENERATED_IMAGES_DIR / image_filename

    try:
        return await _upload_to_catbox(file_path, image_filename)
    except Exception as exc:
        logger.warning("Catbox upload failed: %s — trying Telegram Bot", exc)

    return await _upload_via_telegram(file_path, image_filename)


async def publish_to_facebook(caption: str, hashtags: str, image_filename: str) -> str:
    """Publish a photo post to a Facebook Page via direct file upload (multipart).

    Uses the `source` parameter so Meta doesn't need to download from a URL.
    Returns the Facebook post ID.
    """
    url = f"{GRAPH_API_BASE}/{FACEBOOK_PAGE_ID}/photos"
    message = f"{caption}\n\n{hashtags}"
    file_path = GENERATED_IMAGES_DIR / image_filename

    async with httpx.AsyncClient(timeout=120) as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                url,
                data={
                    "message": message,
                    "access_token": META_ACCESS_TOKEN,
                },
                files={"source": (image_filename, f, "image/png")},
            )

        if not resp.is_success:
            _raise_meta_error(resp, "Facebook")

        data = resp.json()

    post_id = data.get("post_id") or data.get("id", "")
    logger.info("Published to Facebook: %s", post_id)
    return post_id


async def _wait_for_container(client: httpx.AsyncClient, container_id: str, label: str = "") -> None:
    """Poll an Instagram media container until status is FINISHED."""
    import asyncio

    status_url = f"{GRAPH_API_BASE}/{container_id}"
    for attempt in range(15):
        await asyncio.sleep(5)
        resp = await client.get(
            status_url,
            params={"fields": "status_code", "access_token": META_ACCESS_TOKEN},
        )
        if not resp.is_success:
            logger.warning("Instagram status check failed: %s", resp.text)
            continue
        status = resp.json().get("status_code")
        logger.info("Container %s%s status: %s (check %d)", container_id, label, status, attempt + 1)
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Instagram container failed: {resp.json()}")
    raise RuntimeError(f"Container {container_id} not ready after 75s")


async def _publish_ig_single(client: httpx.AsyncClient, image_url: str, caption: str) -> str:
    """Publish a single-image Instagram post."""
    container_url = f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media"
    resp = await client.post(container_url, data={
        "image_url": image_url,
        "caption": caption,
        "access_token": META_ACCESS_TOKEN,
    })
    if not resp.is_success:
        _raise_meta_error(resp, "Instagram")
    creation_id = resp.json()["id"]
    logger.info("Instagram single container: %s", creation_id)

    await _wait_for_container(client, creation_id)

    resp = await client.post(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": META_ACCESS_TOKEN},
    )
    if not resp.is_success:
        _raise_meta_error(resp, "Instagram")
    return resp.json()["id"]


async def _publish_ig_carousel(client: httpx.AsyncClient, image_urls: list[str], caption: str) -> str:
    """Publish a carousel (multi-image) Instagram post.

    Step 1: Create a child container for each image (no caption on children).
    Step 2: Wait for all children to be FINISHED.
    Step 3: Create the carousel container referencing all children.
    Step 4: Wait for the carousel container, then publish.
    """
    child_ids: list[str] = []

    for i, url in enumerate(image_urls):
        resp = await client.post(
            f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media",
            data={
                "image_url": url,
                "is_carousel_item": "true",
                "access_token": META_ACCESS_TOKEN,
            },
        )
        if not resp.is_success:
            _raise_meta_error(resp, f"Instagram child {i + 1}")
        cid = resp.json()["id"]
        child_ids.append(cid)
        logger.info("Instagram carousel child %d/%d: %s", i + 1, len(image_urls), cid)

    for cid in child_ids:
        await _wait_for_container(client, cid, label=" (child)")

    resp = await client.post(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": META_ACCESS_TOKEN,
        },
    )
    if not resp.is_success:
        _raise_meta_error(resp, "Instagram carousel")
    carousel_id = resp.json()["id"]
    logger.info("Instagram carousel container: %s", carousel_id)

    await _wait_for_container(client, carousel_id, label=" (carousel)")

    resp = await client.post(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish",
        data={"creation_id": carousel_id, "access_token": META_ACCESS_TOKEN},
    )
    if not resp.is_success:
        _raise_meta_error(resp, "Instagram publish")
    return resp.json()["id"]


async def publish_to_instagram(hashtags: str, slide_filenames: list[str]) -> str:
    """Compose slides with text-on-image, upload, and publish to Instagram.

    If there is 1 slide  → single image post.
    If there are 2+ slides → carousel post.
    The caption sent to Instagram contains only hashtags (the text is on the images).
    """
    ig_caption = hashtags.strip()

    slide_urls: list[str] = []
    for fname in slide_filenames:
        url = await _upload_for_public_url(fname)
        slide_urls.append(url)

    async with httpx.AsyncClient(timeout=180) as client:
        if len(slide_urls) == 1:
            media_id = await _publish_ig_single(client, slide_urls[0], ig_caption)
        else:
            media_id = await _publish_ig_carousel(client, slide_urls, ig_caption)

    logger.info("Published to Instagram: %s (%d slides)", media_id, len(slide_urls))
    return media_id


async def publish_post(post, db_session) -> None:
    """Orchestrate publication to all selected platforms and update the post record.

    1. Compose text-on-image slides (image_composer).
    2. Facebook: upload the first slide directly.
    3. Instagram: single post or carousel depending on slide count.
    """
    from datetime import datetime, timezone
    from services.image_composer import compose_slides

    filename = post.image_path
    errors: list[str] = []

    slide_filenames = compose_slides(filename, post.caption)
    logger.info("Composed %d slide(s) for post %d", len(slide_filenames), post.id)

    # Facebook — upload first slide with full caption
    try:
        if post.platforms in ("facebook", "both"):
            fb_id = await publish_to_facebook(post.caption, post.hashtags, slide_filenames[0])
            post.fb_post_id = fb_id
    except Exception as exc:
        logger.error("Facebook publish failed for post %d: %s", post.id, exc)
        errors.append(f"Facebook: {exc}")

    # Instagram — text is on the images; only hashtags in caption
    try:
        if post.platforms in ("instagram", "both"):
            ig_id = await publish_to_instagram(post.hashtags, slide_filenames)
            post.ig_post_id = ig_id
    except Exception as exc:
        logger.error("Instagram publish failed for post %d: %s", post.id, exc)
        errors.append(f"Instagram: {exc}")

    if errors:
        post.status = "failed"
        post.error_message = " | ".join(errors)
    else:
        post.status = "published"
        post.published_at = datetime.now(timezone.utc)

    db_session.commit()
    logger.info("Post %d publication result: %s", post.id, post.status)
