import logging
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session


def _format_publish_at(dt: datetime | None) -> str | None:
    """Format a datetime as RFC 3339 with 'Z' for YouTube's publishAt field.

    Our scheduled_at column is naive DateTime but we always store UTC values
    (the frontend pre-converts to UTC). Treat naive as UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%S.0Z')

from backend.config import settings
from backend.database import SessionLocal
from backend.models.upload import Upload
from backend.models.channel import Channel
from backend.models.account import Account
from backend.services.oauth_service import oauth_service
from backend.services.youtube_service import youtube_service, compress_thumbnail
from backend.services.quota_service import quota_service


def _is_inside_temp_dir(file_path: Path) -> bool:
    """Return True iff ``file_path`` lives under settings.temp_dir.

    Safety gate before unlink()ing a "temp" file: a stray bug elsewhere could
    set upload.file_path to anything (e.g. an upstream source the user wanted
    to keep), so we refuse to delete unless the path is actually contained in
    the configured temp directory. Uses string containment on POSIX-style
    paths to dodge Windows-vs-POSIX separator pitfalls and works whether the
    temp dir is the legacy relative ``data/temp`` or an absolute APPDATA path.
    """
    try:
        temp_posix = settings.temp_dir.resolve().as_posix()
    except OSError:
        temp_posix = settings.temp_dir.as_posix()
    try:
        candidate_posix = file_path.resolve().as_posix()
    except OSError:
        candidate_posix = file_path.as_posix()
    # Require a trailing slash so /a/data/temp_bk doesn't match /a/data/temp.
    return candidate_posix.startswith(temp_posix.rstrip("/") + "/")


class UploadManager:
    def __init__(self):
        self._active_jobs: dict[str, bool] = {}
        self._progress_callbacks: dict[str, Callable] = {}
        self._finalize_tasks: dict[str, list[asyncio.Task]] = {}

    def create_job(
        self,
        routing: list[dict],
        thumbnail_path: str | None,
        privacy: str,
        description: str,
        tags: str,
        scheduled_at: str | None,
        db: Session,
        job_id: str | None = None,
    ) -> str:
        """Create upload records and return job_id."""
        if not job_id:
            job_id = str(uuid.uuid4())

        for entry in routing:
            channel = None
            entry_description = description
            if not entry_description:
                channel = db.query(Channel).filter(Channel.id == entry["channel_id"]).first()
                if channel and channel.default_description:
                    entry_description = channel.default_description

            entry_tags = tags
            if not entry_tags:
                if channel is None:
                    channel = db.query(Channel).filter(Channel.id == entry["channel_id"]).first()
                if channel and channel.default_tags:
                    entry_tags = channel.default_tags

            title = entry.get("title") or (entry["file_name"].rsplit(".", 1)[0] if "." in entry["file_name"] else entry["file_name"])
            entry_scheduled_at_str = entry.get("scheduled_at") or scheduled_at
            upload = Upload(
                job_id=job_id,
                channel_id=entry["channel_id"],
                file_path=entry["file_path"],
                file_name=entry["file_name"],
                title=title[:100],
                description=entry_description,
                tags=entry_tags,
                privacy=privacy,
                scheduled_at=datetime.fromisoformat(entry_scheduled_at_str) if entry_scheduled_at_str else None,
                thumbnail_path=entry.get("thumbnail_path") or thumbnail_path,
                detected_language=entry.get("detected_language"),
                detection_method=entry.get("detection_method"),
                status="pending",
                quota_cost=150 if thumbnail_path else 100,
            )
            db.add(upload)

        db.commit()
        return job_id

    def set_progress_callback(self, job_id: str, callback: Callable):
        self._progress_callbacks[job_id] = callback

    def remove_progress_callback(self, job_id: str):
        self._progress_callbacks.pop(job_id, None)

    async def _finalize_after_insert(
        self,
        job_id: str,
        upload_id: int,
        video_id: str,
        youtube_url: str,
        yt_service,
        thumbnail_path: str | None,
        default_comment: str | None,
        project_id: int,
        callback,
    ):
        """All the post-insert work for a single upload (verify polling, thumbnail,
        comment, completion bookkeeping, cleanup, upload_completed event).

        Runs as its own asyncio.Task so multiple uploads can be in the
        post-insert phase concurrently. Opens its OWN SessionLocal because
        SQLAlchemy Session objects are not safe to share across tasks.
        """
        loop = asyncio.get_event_loop()
        local_db = SessionLocal()
        try:
            upload = local_db.query(Upload).filter(Upload.id == upload_id).first()
            if upload is None:
                logger.error("finalize: upload %d not found", upload_id)
                return

            # Persist the YouTube ids first thing — even if anything below blows
            # up, we don't want to lose the link to the live video.
            upload.youtube_video_id = video_id
            upload.youtube_url = youtube_url
            upload.progress_percent = 100
            local_db.commit()

            # Stage 3: verify YouTube processing
            try:
                if callback:
                    await callback({
                        "type": "youtube_processing_started",
                        "upload_id": upload.id,
                    })
                POLL_MAX = 1440
                POLL_INTERVAL = 15
                final_status = None
                for _ in range(POLL_MAX):
                    try:
                        details = await loop.run_in_executor(
                            None,
                            lambda: yt_service.videos().list(
                                part="status,processingDetails",
                                id=video_id,
                            ).execute(),
                        )
                    except Exception as exc:
                        logger.warning("processingDetails poll failed for upload %d: %s", upload.id, exc)
                        error_str = f"polling error: {exc}"
                        upload.verification_error = error_str
                        local_db.commit()
                        if callback:
                            await callback({
                                "type": "verification_failed",
                                "upload_id": upload.id,
                                "error": error_str,
                            })
                        break
                    items = details.get("items", [])
                    if not items:
                        break
                    item = items[0]
                    upload_status = (item.get("status") or {}).get("uploadStatus")
                    processing = item.get("processingDetails") or {}
                    processing_status = processing.get("processingStatus")
                    progress = processing.get("processingProgress") or {}
                    parts_processed = int(progress.get("partsProcessed") or 0)
                    parts_total = int(progress.get("partsTotal") or 0)
                    percent = (parts_processed / parts_total * 100) if parts_total else None
                    if callback:
                        await callback({
                            "type": "youtube_processing_progress",
                            "upload_id": upload.id,
                            "upload_status": upload_status,
                            "processing_status": processing_status,
                            "parts_processed": parts_processed,
                            "parts_total": parts_total,
                            "percent": round(percent, 1) if percent is not None else None,
                        })
                    if upload_status in ("processed",) or processing_status in ("succeeded",):
                        final_status = processing_status or upload_status
                        break
                    if upload_status in ("failed", "rejected") or processing_status in ("failed", "terminated"):
                        final_status = processing_status or upload_status
                        error_str = final_status or "unknown"
                        upload.verification_error = error_str
                        local_db.commit()
                        if callback:
                            await callback({
                                "type": "verification_failed",
                                "upload_id": upload.id,
                                "error": error_str,
                            })
                        break
                    await asyncio.sleep(POLL_INTERVAL)
                if callback:
                    await callback({
                        "type": "youtube_processing_completed",
                        "upload_id": upload.id,
                        "final_status": final_status,
                    })
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("youtube_processing block raised for upload %d: %s", upload.id, e)
                # Never fail the upload because of polling — the video is already on YouTube.

            thumbnail_error = None

            if thumbnail_path:
                try:
                    if callback:
                        await callback({
                            "type": "thumbnail_applying",
                            "upload_id": upload.id,
                        })
                    compressed_path = compress_thumbnail(thumbnail_path)
                    thumb_to_upload = compressed_path or thumbnail_path
                    try:
                        success = youtube_service.set_thumbnail(yt_service, video_id, thumb_to_upload)
                        if not success:
                            thumbnail_error = "Thumbnail upload returned failure"
                            logger.warning("Thumbnail not set for upload %d (returned False)", upload.id)
                    finally:
                        if compressed_path:
                            try:
                                Path(compressed_path).unlink(missing_ok=True)
                            except OSError:
                                pass
                    if callback and not thumbnail_error:
                        await callback({
                            "type": "thumbnail_set",
                            "upload_id": upload.id,
                        })
                    elif callback and thumbnail_error:
                        upload.thumbnail_error = thumbnail_error
                        local_db.commit()
                        await callback({
                            "type": "thumbnail_failed",
                            "upload_id": upload.id,
                            "error": thumbnail_error,
                        })
                    elif thumbnail_error:
                        upload.thumbnail_error = thumbnail_error
                        local_db.commit()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    thumbnail_error = str(e)
                    logger.error("Thumbnail failed for upload %d but video is uploaded: %s", upload.id, e)
                    upload.thumbnail_error = thumbnail_error
                    local_db.commit()
                    if callback:
                        await callback({
                            "type": "thumbnail_failed",
                            "upload_id": upload.id,
                            "error": str(e),
                        })
                    # DON'T re-raise — the video is already on YouTube

            # Auto-post the channel's default comment (non-fatal — video is already live)
            if default_comment:
                try:
                    if callback:
                        await callback({
                            "type": "comment_posting",
                            "upload_id": upload.id,
                        })
                    youtube_service.post_comment(
                        yt_service,
                        video_id,
                        default_comment,
                    )
                    if callback:
                        await callback({
                            "type": "comment_posted",
                            "upload_id": upload.id,
                        })
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(
                        "Comment post failed for upload %d but video is uploaded: %s",
                        upload.id, e,
                    )
                    upload.comment_error = str(e)
                    local_db.commit()
                    if callback:
                        await callback({
                            "type": "comment_failed",
                            "upload_id": upload.id,
                            "error": str(e),
                        })
                    # DON'T re-raise — the video is already on YouTube

            upload.status = "completed"
            upload.completed_at = datetime.utcnow()
            local_db.commit()

            # Clean up temp file after successful upload
            try:
                temp_path = Path(upload.file_path)
                if temp_path.exists() and _is_inside_temp_dir(temp_path):
                    temp_path.unlink()
            except OSError:
                pass

            if callback:
                await callback({
                    "type": "upload_completed",
                    "upload_id": upload.id,
                    "youtube_url": upload.youtube_url,
                    "thumbnail_error": thumbnail_error,
                })

        except asyncio.CancelledError:
            # Mark as failed if we got canceled mid-finalize
            try:
                upload = local_db.query(Upload).filter(Upload.id == upload_id).first()
                if upload and upload.status not in ("completed", "failed"):
                    upload.status = "failed"
                    upload.error_message = "Canceled"
                    local_db.commit()
            except Exception:
                pass
            raise
        except Exception as e:
            logger.exception("finalize task crashed for upload %d: %s", upload_id, e)
            try:
                upload = local_db.query(Upload).filter(Upload.id == upload_id).first()
                if upload:
                    upload.status = "failed"
                    upload.error_message = str(e)
                    local_db.commit()
            except Exception:
                pass
            if callback:
                try:
                    await callback({
                        "type": "upload_failed",
                        "upload_id": upload_id,
                        "error": str(e),
                    })
                except Exception:
                    pass
        finally:
            local_db.close()

    async def process_job(self, job_id: str):
        """Process all uploads in a job.

        The byte-stream `videos.insert` portion runs sequentially in the for
        loop (only one upload sending bytes at a time). The post-insert work
        (verify polling, thumbnail, comment) is dispatched as an asyncio.Task
        so the next upload can start streaming bytes while the previous one
        is still finalizing.
        """
        # Allow WebSocket client time to connect before sending events
        await asyncio.sleep(1)
        self._active_jobs[job_id] = True
        self._finalize_tasks.setdefault(job_id, [])
        db = SessionLocal()

        try:
            uploads = db.query(Upload).filter(Upload.job_id == job_id, Upload.status == "pending").all()
            total = len(uploads)
            callback = self._progress_callbacks.get(job_id)

            if callback:
                await callback({
                    "type": "job_started",
                    "job_id": job_id,
                    "total_files": total,
                })

            for upload in uploads:
                if not self._active_jobs.get(job_id):
                    break

                # Resolve channel/account/creds BEFORE upload_started so that
                # the started event can include has_thumbnail / has_comment.
                # If any of these fail, emit upload_failed (not upload_started).
                try:
                    channel = db.query(Channel).filter(Channel.id == upload.channel_id).first()
                    if not channel:
                        raise Exception("Channel not found")

                    account = db.query(Account).filter(Account.id == channel.account_id).first()
                    if not account:
                        raise Exception("Account not found")

                    creds = oauth_service.load_credentials(account.token_path)
                    if not creds:
                        raise Exception("Invalid credentials")

                    yt_service = oauth_service.get_youtube_service(creds)
                except Exception as e:
                    upload.status = "failed"
                    upload.error_message = str(e)
                    db.commit()
                    if callback:
                        await callback({
                            "type": "upload_failed",
                            "upload_id": upload.id,
                            "error": str(e),
                        })
                    continue

                upload.status = "uploading"
                db.commit()

                if callback:
                    await callback({
                        "type": "upload_started",
                        "upload_id": upload.id,
                        "file_name": upload.file_name,
                        "channel_name": channel.channel_name if channel else "Unknown",
                        "has_thumbnail": bool(upload.thumbnail_path),
                        "has_comment": bool(channel.default_comment),
                    })

                try:
                    # Record quota usage BEFORE dispatching the upload. YouTube
                    # debits us for videos.insert whether the upload ultimately
                    # succeeds or fails, so we must record it once per attempt.
                    try:
                        quota_service.record_usage(
                            project_id=account.project_id,
                            units=upload.quota_cost or 100,
                            db=db,
                        )
                    except Exception:
                        pass  # Don't fail the upload if quota tracking fails

                    loop = asyncio.get_event_loop()

                    upload_id_for_progress = upload.id

                    def sync_progress(percent, _uid=upload_id_for_progress):
                        # This runs in a worker thread, so use thread-safe call
                        if callback:
                            asyncio.run_coroutine_threadsafe(
                                callback({
                                    "type": "upload_progress",
                                    "upload_id": _uid,
                                    "percent": round(percent, 1),
                                }),
                                loop,
                            )

                    upload_language = (
                        upload.detected_language
                        if upload.detected_language
                        else (channel.language_code if channel.language_code else None)
                    )

                    result = await loop.run_in_executor(
                        None,
                        lambda: youtube_service.upload_video(
                            youtube_service=yt_service,
                            file_path=upload.file_path,
                            title=upload.title,
                            description=upload.description,
                            tags=upload.tags,
                            privacy=upload.privacy,
                            publish_at=_format_publish_at(upload.scheduled_at),
                            language=upload_language,
                            on_progress=sync_progress,
                        ),
                    )

                    # Dispatch the post-insert finalize work as a background
                    # task so the next upload can start streaming bytes.
                    task = asyncio.create_task(
                        self._finalize_after_insert(
                            job_id=job_id,
                            upload_id=upload.id,
                            video_id=result["video_id"],
                            youtube_url=result["youtube_url"],
                            yt_service=yt_service,
                            thumbnail_path=upload.thumbnail_path,
                            default_comment=channel.default_comment,
                            project_id=account.project_id,
                            callback=callback,
                        )
                    )
                    self._finalize_tasks.setdefault(job_id, []).append(task)

                except Exception as e:
                    upload.status = "failed"
                    upload.error_message = str(e)
                    db.commit()

                    # Clean up temp file even on failure
                    try:
                        temp_path = Path(upload.file_path)
                        if temp_path.exists() and _is_inside_temp_dir(temp_path):
                            temp_path.unlink()
                    except OSError:
                        pass

                    if callback:
                        await callback({
                            "type": "upload_failed",
                            "upload_id": upload.id,
                            "error": str(e),
                        })

            # Wait for all finalize tasks before emitting job_completed.
            # NOTE: do not pop the list here — cancel_job needs to be able to
            # reach the in-flight tasks. We pop in the outer `finally`.
            pending = list(self._finalize_tasks.get(job_id, []))
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            # Count succeeded/failed by querying the DB (each finalize task
            # committed its own row using its own session).
            db.expire_all()
            final_uploads = db.query(Upload).filter(Upload.job_id == job_id).all()
            succeeded = sum(1 for u in final_uploads if u.status == "completed")
            failed = sum(1 for u in final_uploads if u.status == "failed")

            if callback:
                await callback({
                    "type": "job_completed",
                    "job_id": job_id,
                    "succeeded": succeeded,
                    "failed": failed,
                })

        finally:
            self._active_jobs.pop(job_id, None)
            self._finalize_tasks.pop(job_id, None)
            db.close()

    def cancel_job(self, job_id: str):
        """Cancel a running job. Stops the main loop AND cancels any in-flight
        finalize tasks for this job."""
        self._active_jobs[job_id] = False
        for task in self._finalize_tasks.get(job_id, []):
            if not task.done():
                task.cancel()


upload_manager = UploadManager()
