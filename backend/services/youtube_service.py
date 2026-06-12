import logging
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Callable

from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)

YOUTUBE_THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


def compress_thumbnail(image_path: str) -> str | None:
    """
    If the thumbnail file exceeds YouTube's 2MB limit, compress it by
    converting to JPEG and progressively reducing quality.  Returns the
    path to a temp file (caller must delete) or *None* when the original
    is already small enough.
    """
    file_size = os.path.getsize(image_path)
    if file_size <= YOUTUBE_THUMBNAIL_MAX_BYTES:
        return None  # no compression needed

    logger.info(
        "Thumbnail %s is %d bytes (%.1f KB), exceeds 2 MB – compressing",
        image_path, file_size, file_size / 1024,
    )

    img = Image.open(image_path)
    # Convert to RGB if necessary (e.g. RGBA PNGs, palette images)
    if img.mode not in ("RGB",):
        img = img.convert("RGB")

    # Try progressively lower JPEG quality until under the limit
    for quality in range(90, 10, -5):
        tmp = tempfile.NamedTemporaryFile(
            suffix=".jpg", delete=False, dir=tempfile.gettempdir(),
        )
        tmp_path = tmp.name
        tmp.close()

        img.save(tmp_path, format="JPEG", quality=quality, optimize=True)
        compressed_size = os.path.getsize(tmp_path)

        if compressed_size <= YOUTUBE_THUMBNAIL_MAX_BYTES:
            logger.info(
                "Compressed thumbnail to %d bytes (quality=%d): %s",
                compressed_size, quality, tmp_path,
            )
            return tmp_path

        # This quality level wasn't enough – remove and try lower
        os.unlink(tmp_path)

    # Quality alone wasn't enough; resize the image and retry
    logger.info("Quality reduction insufficient, resizing thumbnail")
    for scale in (0.75, 0.5, 0.4, 0.3):
        resized = img.resize(
            (int(img.width * scale), int(img.height * scale)),
            Image.LANCZOS,
        )
        tmp = tempfile.NamedTemporaryFile(
            suffix=".jpg", delete=False, dir=tempfile.gettempdir(),
        )
        tmp_path = tmp.name
        tmp.close()

        resized.save(tmp_path, format="JPEG", quality=80, optimize=True)
        compressed_size = os.path.getsize(tmp_path)

        if compressed_size <= YOUTUBE_THUMBNAIL_MAX_BYTES:
            logger.info(
                "Compressed+resized thumbnail to %d bytes (scale=%.0f%%): %s",
                compressed_size, scale * 100, tmp_path,
            )
            return tmp_path

        os.unlink(tmp_path)

    logger.error("Failed to compress thumbnail under 2 MB: %s", image_path)
    return None

RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
RETRIABLE_EXCEPTIONS = (IOError, ConnectionError, TimeoutError)
MAX_RETRIES = 10


class YouTubeService:
    def upload_video(
        self,
        youtube_service,
        file_path: str,
        title: str,
        description: str = "",
        tags: str = "",
        privacy: str = "private",
        category_id: str = "22",  # People & Blogs
        publish_at: str | None = None,
        language: str | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> dict:
        """
        Upload a video using resumable upload protocol.
        Returns dict with video_id and youtube_url.
        """
        snippet = {
            "title": title[:100],
            "description": description,
            "tags": [t.strip() for t in tags.split(",") if t.strip()] if tags else [],
            "categoryId": category_id,
        }

        if language:
            snippet["defaultLanguage"] = language
            snippet["defaultAudioLanguage"] = language

        body = {
            "snippet": snippet,
            "status": {
                "privacyStatus": "private" if publish_at else privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        if publish_at:
            body["status"]["publishAt"] = publish_at

        chunk_size = settings.upload_chunk_size_mb * 1024 * 1024
        media = MediaFileUpload(
            file_path,
            chunksize=chunk_size,
            resumable=True,
        )

        request = youtube_service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        retry_count = 0

        while response is None:
            try:
                status, response = request.next_chunk()
                if status and on_progress:
                    on_progress(status.progress() * 100)
            except HttpError as e:
                if e.resp.status in RETRIABLE_STATUS_CODES:
                    retry_count += 1
                    if retry_count > MAX_RETRIES:
                        raise
                    sleep_time = min(2 ** retry_count + random.random(), 60)
                    time.sleep(sleep_time)
                else:
                    raise
            except RETRIABLE_EXCEPTIONS:
                retry_count += 1
                if retry_count > MAX_RETRIES:
                    raise
                sleep_time = min(2 ** retry_count + random.random(), 60)
                time.sleep(sleep_time)

        if on_progress:
            on_progress(100)

        video_id = response["id"]
        return {
            "video_id": video_id,
            "youtube_url": f"https://youtu.be/{video_id}",
        }

    def set_thumbnail(self, youtube_service, video_id: str, image_path: str) -> bool:
        """Upload a custom thumbnail for a video."""
        if not Path(image_path).exists():
            logger.warning("Thumbnail file not found: %s", image_path)
            return False

        media = MediaFileUpload(image_path, mimetype="image/jpeg")
        try:
            youtube_service.thumbnails().set(
                videoId=video_id,
                media_body=media,
            ).execute()
            logger.info("Thumbnail set successfully for video %s", video_id)
            return True
        except Exception as e:
            logger.error("Failed to set thumbnail for video %s: %s", video_id, e)
            return False

    def post_comment(self, youtube_service, video_id: str, text: str):
        """Post a top-level comment on a video. Non-fatal; returns None on failure.

        Note: YouTube's API can post a comment but cannot pin it.
        """
        try:
            response = youtube_service.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {"textOriginal": text},
                        },
                    },
                },
            ).execute()
            logger.info("Posted comment on video %s", video_id)
            return response
        except Exception as e:
            logger.error("Failed to post comment on video %s: %s", video_id, e)
            return None


    def get_video_status(self, youtube_service, video_id: str) -> dict:
        """Get processing status of an uploaded video."""
        try:
            response = youtube_service.videos().list(
                part="status,processingDetails",
                id=video_id,
            ).execute()

            if not response.get("items"):
                return {"status": "not_found"}

            item = response["items"][0]
            status = item.get("status", {})
            processing = item.get("processingDetails", {})

            return {
                "upload_status": status.get("uploadStatus", "unknown"),
                "privacy_status": status.get("privacyStatus", "unknown"),
                "processing_status": processing.get("processingStatus", "unknown"),
            }
        except HttpError:
            return {"status": "error"}


    def update_video(
        self,
        youtube_service,
        video_id: str,
        title: str,
        description: str,
        tags: str,
        privacy: str,
    ) -> dict:
        """Update the snippet/status of an already-uploaded video."""
        snippet = {
            "title": title[:100],
            "description": description,
            "tags": [t.strip() for t in tags.split(",") if t.strip()] if tags else [],
            "categoryId": "22",
        }
        response = youtube_service.videos().update(
            part="snippet,status",
            body={
                "id": video_id,
                "snippet": snippet,
                "status": {"privacyStatus": privacy},
            },
        ).execute()
        logger.info("Updated video %s metadata (privacy=%s)", video_id, privacy)
        return response


youtube_service = YouTubeService()
