import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import settings as app_settings
from backend.database import get_db
from backend.models.upload import Upload
from backend.models.channel import Channel
from backend.models.account import Account
from backend.models.language_schedule import LanguageSchedule
from backend.schemas.language_schedule import (
    ResolvedSchedule,
    ResolveScheduleRequest,
)
from backend.schemas.upload import (
    JobSummary,
    PrepareRequest,
    PrepareResponse,
    RoutingEntry,
    StartUploadRequest,
    UploadResponse,
    YoutubeEditRequest,
)
from backend.services.youtube_service import youtube_service as youtube_service_instance

_BRT_TZ = ZoneInfo("America/Sao_Paulo")


def _get_now_brt() -> datetime:
    """Current time in BRT. Indirected through a helper so tests can patch it."""
    return datetime.now(_BRT_TZ)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


# NOTE: /resolve-schedule is declared near the top of the router so FastAPI
# matches the literal before any later /{upload_id} style routes (e.g.
# /{upload_id}/youtube or /video-status/{upload_id}).
@router.post("/resolve-schedule", response_model=list[ResolvedSchedule])
def resolve_schedule(
    body: ResolveScheduleRequest,
    db: Session = Depends(get_db),
    _now: datetime | None = None,
):
    """Resolve each channel's effective posting time for "today" in BRT.

    Precedence: channel.custom_schedule_time > language_schedules row > none.
    BRT->UTC conversion uses fixed America/Sao_Paulo (effectively UTC-3).

    `_now` is an optional injection point for tests; if omitted we use the
    real current time via _get_now_brt(). Tests can also monkeypatch
    backend.api.uploads._get_now_brt directly.
    """
    now_brt = _now if _now is not None else _get_now_brt()
    if now_brt.tzinfo is None:
        # If a naive datetime was passed in tests, treat as BRT.
        now_brt = now_brt.replace(tzinfo=_BRT_TZ)
    today_brt = now_brt.date()
    # `target_date` (if provided) selects the calendar day in BRT to combine
    # with each channel's HH:MM preset. Defaults to today in BRT.
    today = body.target_date or today_brt

    results: list[ResolvedSchedule] = []
    for cid in body.channel_ids:
        channel = db.query(Channel).filter(Channel.id == cid).first()
        if channel is None:
            results.append(
                ResolvedSchedule(
                    channel_id=cid,
                    channel_name="",
                    language_code=None,
                    resolved_time=None,
                    source="none",
                    scheduled_at_brt=None,
                    scheduled_at_utc=None,
                    already_passed=False,
                    error="Channel not found",
                )
            )
            continue

        resolved_time: str | None = None
        source = "none"
        if channel.custom_schedule_time:
            resolved_time = channel.custom_schedule_time
            source = "channel"
        elif channel.language_code:
            lang_row = (
                db.query(LanguageSchedule)
                .filter(LanguageSchedule.language_code == channel.language_code)
                .first()
            )
            if lang_row:
                resolved_time = lang_row.time_brt
                source = "language"

        if resolved_time:
            hh, mm = resolved_time.split(":")
            scheduled_at_brt = datetime(
                today.year,
                today.month,
                today.day,
                int(hh),
                int(mm),
                tzinfo=_BRT_TZ,
            )
            scheduled_at_utc = scheduled_at_brt.astimezone(timezone.utc)
            already_passed = scheduled_at_brt <= now_brt
            results.append(
                ResolvedSchedule(
                    channel_id=channel.id,
                    channel_name=channel.channel_name,
                    language_code=channel.language_code or None,
                    resolved_time=resolved_time,
                    source=source,
                    scheduled_at_brt=scheduled_at_brt,
                    scheduled_at_utc=scheduled_at_utc,
                    already_passed=already_passed,
                    error=None,
                )
            )
        else:
            lang_display = channel.language_code or "?"
            results.append(
                ResolvedSchedule(
                    channel_id=channel.id,
                    channel_name=channel.channel_name,
                    language_code=channel.language_code or None,
                    resolved_time=None,
                    source="none",
                    scheduled_at_brt=None,
                    scheduled_at_utc=None,
                    already_passed=False,
                    error=f"No schedule configured for language {lang_display}",
                )
            )
    return results


@router.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    """Receive a video/image file from the browser and save to temp directory."""
    # Resolve at call time so POSTBELL_DATA_DIR overrides take effect even if
    # they were applied after this module was imported.
    temp_dir = app_settings.temp_dir
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Use original filename, sanitize slightly
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    dest = temp_dir / safe_name

    # If file already exists with same name, add a suffix
    counter = 1
    while dest.exists():
        stem = Path(safe_name).stem
        ext = Path(safe_name).suffix
        dest = temp_dir / f"{stem}_{counter}{ext}"
        counter += 1

    with open(dest, "wb") as f:
        # Stream in chunks to handle large files
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            f.write(chunk)

    return {"path": str(dest.resolve()), "name": file.filename}


# ---------------------------------------------------------------------------
# Chunked upload (additional path, see /upload-chunk + /finalize-chunked).
#
# Rationale: the existing /upload-file streams the request body to disk, so
# memory is not the bottleneck. The point of chunking here is to:
#   * avoid a single long-lived HTTP connection on slow networks (proxy
#     timeouts, transient drops),
#   * give the frontend reliable per-chunk progress updates,
#   * make a future retry-per-chunk feature straightforward.
#
# Chunks live in temp_dir / ".chunks" / <upload_id> / chunk-NNNN and are
# assembled into the final file by /finalize-chunked, which then deletes the
# scratch directory. The directory name starts with "." so it is visually
# segregated from real uploads in temp/.
# ---------------------------------------------------------------------------

_CHUNKS_DIRNAME = ".chunks"
_UPLOAD_ID_RE = re.compile(r"^[a-f0-9-]{36}$")
_MAX_TOTAL_CHUNKS = 1000
# Pad chunk indices to 4 digits so glob-sorting matches numeric order up to
# _MAX_TOTAL_CHUNKS (1000 < 10_000 -> 4 digits is enough).
_CHUNK_NAME_FMT = "chunk-{:04d}"


def _sanitize_upload_id(upload_id: str) -> str:
    """Validate upload_id is a lowercase UUID. Reject anything else.

    Accepting only the strict UUID shape closes the path-traversal vector for
    the per-upload chunks directory (no '..', '/', '\\' can sneak through).
    """
    if not upload_id or not _UPLOAD_ID_RE.match(upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id (expected UUID).")
    return upload_id


def _sanitize_filename(filename: str) -> str:
    """Strip directory separators from a client-supplied filename."""
    if not filename:
        raise HTTPException(status_code=400, detail="Filename required.")
    return filename.replace("/", "_").replace("\\", "_").replace("..", "_")


def _chunks_root() -> Path:
    """Resolve temp_dir/.chunks at call time so POSTBELL_DATA_DIR overrides apply."""
    root = app_settings.temp_dir / _CHUNKS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post("/upload-chunk")
async def upload_chunk(
    request: Request,
    x_upload_id: str = Header(...),
    x_chunk_index: int = Header(...),
    x_total_chunks: int = Header(...),
    x_filename: str = Header(...),
):
    """Receive one chunk of a chunked upload, write it to a per-upload scratch dir.

    Headers:
      X-Upload-Id     : UUIDv4-shaped string (client-generated).
      X-Chunk-Index   : 0-based chunk index.
      X-Total-Chunks  : total number of chunks the client intends to send.
      X-Filename      : final filename (sanitized later at finalize time).

    Body: raw chunk bytes (NOT multipart). Stored as chunks_root/<id>/chunk-NNNN.

    Dup-detection: if a chunk for (upload_id, chunk_index) already exists with
    a different size than the incoming body, we refuse with 409 instead of
    silently overwriting. Equal-size re-sends are accepted as idempotent
    retries.
    """
    upload_id = _sanitize_upload_id(x_upload_id)
    # `x_filename` is validated here so the client gets early feedback, but
    # the path sanitization that picks the final dest is in /finalize-chunked.
    _ = _sanitize_filename(x_filename)

    if not (1 <= x_total_chunks <= _MAX_TOTAL_CHUNKS):
        raise HTTPException(
            status_code=400,
            detail=f"total_chunks out of range (1..{_MAX_TOTAL_CHUNKS}).",
        )
    if not (0 <= x_chunk_index < x_total_chunks):
        raise HTTPException(
            status_code=400,
            detail="chunk_index must satisfy 0 <= index < total_chunks.",
        )

    chunk_dir = _chunks_root() / upload_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunk_dir / _CHUNK_NAME_FMT.format(x_chunk_index)

    # Buffer the incoming body in memory long enough to know its size before
    # deciding whether to overwrite a pre-existing chunk. Chunks are bounded
    # by the frontend to ~50MB which is comfortable for a temporary buffer.
    body = await request.body()
    incoming_size = len(body)

    if chunk_path.exists():
        existing_size = chunk_path.stat().st_size
        if existing_size != incoming_size:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"chunk {x_chunk_index} already received with size "
                    f"{existing_size}; refusing overwrite with size {incoming_size}"
                ),
            )
        # Same size -> treat as idempotent retry; nothing to do.
    else:
        with open(chunk_path, "wb") as f:
            f.write(body)

    return {"chunk_index": x_chunk_index, "received": True, "size": incoming_size}


class FinalizeChunkedRequest(BaseModel):
    upload_id: str
    filename: str
    total_chunks: int


@router.post("/finalize-chunked")
def finalize_chunked(req: FinalizeChunkedRequest):
    """Assemble all chunks for upload_id into temp_dir/<safe_filename>.

    Mirrors the sanitization + collision logic of /upload-file so callers see
    the same response shape regardless of which upload path was used.
    """
    upload_id = _sanitize_upload_id(req.upload_id)
    safe_name = _sanitize_filename(req.filename)

    if not (1 <= req.total_chunks <= _MAX_TOTAL_CHUNKS):
        raise HTTPException(
            status_code=400,
            detail=f"total_chunks out of range (1..{_MAX_TOTAL_CHUNKS}).",
        )

    chunk_dir = _chunks_root() / upload_id
    if not chunk_dir.is_dir():
        raise HTTPException(status_code=404, detail="No chunks found for upload_id.")

    # Verify every expected chunk exists.
    missing: list[int] = []
    for i in range(req.total_chunks):
        if not (chunk_dir / _CHUNK_NAME_FMT.format(i)).exists():
            missing.append(i)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing chunks: {missing[:10]}{'...' if len(missing) > 10 else ''}",
        )

    # Resolve the final destination with the same collision-suffix logic as
    # /upload-file. temp_dir is computed at call-time so POSTBELL_DATA_DIR
    # overrides win even when they're applied after module import.
    temp_dir = app_settings.temp_dir
    temp_dir.mkdir(parents=True, exist_ok=True)
    dest = temp_dir / safe_name
    counter = 1
    while dest.exists():
        stem = Path(safe_name).stem
        ext = Path(safe_name).suffix
        dest = temp_dir / f"{stem}_{counter}{ext}"
        counter += 1

    # Concatenate chunks in index order. shutil.copyfileobj streams chunk file
    # -> dest file via a small internal buffer (no full chunk in RAM).
    with open(dest, "wb") as out:
        for i in range(req.total_chunks):
            chunk_path = chunk_dir / _CHUNK_NAME_FMT.format(i)
            with open(chunk_path, "rb") as src:
                shutil.copyfileobj(src, out)

    # Best-effort cleanup of the scratch directory.
    try:
        shutil.rmtree(chunk_dir, ignore_errors=True)
    except Exception:
        # Cleanup failure is non-fatal — the worst case is a stale scratch
        # dir that can be removed manually. We don't want to fail the upload
        # over it.
        pass

    return {"path": str(dest.resolve()), "name": req.filename}


@router.post("/prepare", response_model=PrepareResponse)
def prepare_upload(req: PrepareRequest, db: Session = Depends(get_db)):
    """Analyze files, detect languages, and route to channels."""
    from backend.services.routing_service import routing_service

    file_names = [f.name for f in req.files]
    file_paths = [f.path for f in req.files]

    routed, unroutable = routing_service.route_files(
        file_names, file_paths, req.selected_channel_ids, db
    )

    return PrepareResponse(routing=routed, unroutable=unroutable)


@router.get("")
def list_uploads(
    page: int = 1,
    per_page: int = 20,
    status: str | None = None,
    channel_id: int | None = None,
    db: Session = Depends(get_db),
):
    """List upload history with pagination, optional status and channel filters."""
    query = db.query(Upload)
    if status:
        query = query.filter(Upload.status == status)
    if channel_id is not None:
        query = query.filter(Upload.channel_id == channel_id)
    total = query.count()
    offset = (page - 1) * per_page
    uploads = query.order_by(Upload.created_at.desc()).offset(offset).limit(per_page).all()
    return {"items": uploads, "total": total, "page": page, "per_page": per_page}


@router.get("/scheduled")
def list_scheduled_uploads(db: Session = Depends(get_db)):
    """Return upcoming scheduled uploads (pending or uploading, scheduled_at in the future)."""
    now = datetime.utcnow()
    uploads = (
        db.query(Upload)
        .filter(
            Upload.scheduled_at > now,
            Upload.status.in_(["pending", "uploading"]),
        )
        .order_by(Upload.scheduled_at.asc())
        .all()
    )
    return {
        "items": [
            {
                "id": u.id,
                "job_id": u.job_id,
                "file_name": u.file_name,
                "title": u.title,
                "channel_id": u.channel_id,
                "privacy": u.privacy,
                "scheduled_at": u.scheduled_at.isoformat() if u.scheduled_at else None,
                "status": u.status,
            }
            for u in uploads
        ]
    }


@router.post("/start")
async def start_upload(req: StartUploadRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Start an upload job."""
    from backend.services.upload_manager import upload_manager
    from backend.api.ws import manager as ws_manager

    base_scheduled_at: datetime | None = None
    if req.scheduled_at:
        base_scheduled_at = datetime.fromisoformat(req.scheduled_at)

    # Auto-agendar (per-language) mode: the frontend computes each entry's own
    # publish time and attaches it as RoutingEntry.scheduled_at. That per-entry
    # value MUST take precedence over the job-level + stagger fallback below;
    # without this the per-language schedules silently collapse to None.
    routing_dicts = []
    for i, entry in enumerate(req.routing):
        d = entry.model_dump()
        if entry.scheduled_at:
            # Per-entry value already an ISO string from the frontend; keep
            # verbatim so create_job can parse it.
            d["scheduled_at"] = entry.scheduled_at
        elif base_scheduled_at is not None:
            # Legacy: job-level scheduled_at + stagger (first entry no offset).
            if req.stagger_minutes and i > 0:
                stagger_dt = base_scheduled_at + timedelta(minutes=req.stagger_minutes * i)
            else:
                stagger_dt = base_scheduled_at
            d["scheduled_at"] = stagger_dt.isoformat()
        else:
            d["scheduled_at"] = None
        routing_dicts.append(d)

    # If ANY upload row will be scheduled, the whole job's privacy must be
    # 'private' — YouTube only honours publishAt on private videos. The
    # frontend already enforces this in auto_lang mode, but force it server-
    # side too so a stale/legacy client cannot create a public+scheduled job.
    has_any_schedule = any(d["scheduled_at"] is not None for d in routing_dicts)
    effective_privacy = req.privacy
    if has_any_schedule and req.privacy != "private":
        effective_privacy = "private"

    job_id = upload_manager.create_job(
        routing=routing_dicts,
        thumbnail_path=req.thumbnail_path,
        privacy=effective_privacy,
        description=req.description,
        tags=req.tags,
        scheduled_at=req.scheduled_at,
        db=db,
        job_id=req.job_id,
    )

    async def ws_callback(event):
        await ws_manager.send_event(job_id, event)

    upload_manager.set_progress_callback(job_id, ws_callback)
    background_tasks.add_task(upload_manager.process_job, job_id)

    return {"job_id": job_id}


def _derive_job_status(statuses: list[str]) -> str:
    """Map a list of per-upload statuses to a single job-level status.

    'running'    -> any upload still pending or uploading
    'completed'  -> every upload completed
    'failed'     -> every upload failed
    'partial'    -> mix of completed and failed (terminal but not uniform)
    """
    if any(s in ("pending", "uploading") for s in statuses):
        return "running"
    if all(s == "completed" for s in statuses):
        return "completed"
    if all(s == "failed" for s in statuses):
        return "failed"
    return "partial"


@router.get("/jobs/recent", response_model=list[JobSummary])
def list_recent_jobs(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Return up to `limit` most-recent upload jobs as summaries.

    Each summary aggregates the rows belonging to a job_id: total/completed/
    failed counts, an in_flight count (pending + uploading), the earliest
    created_at as the job started_at, and a derived job-level status.
    Sorted by started_at descending.
    """
    uploads = db.query(Upload).all()
    by_job: dict[str, list[Upload]] = {}
    for u in uploads:
        by_job.setdefault(u.job_id, []).append(u)

    summaries: list[JobSummary] = []
    for job_id, rows in by_job.items():
        statuses = [r.status for r in rows]
        started_at = min(r.created_at for r in rows)
        completed = sum(1 for s in statuses if s == "completed")
        failed = sum(1 for s in statuses if s == "failed")
        in_flight = sum(1 for s in statuses if s in ("pending", "uploading"))
        summaries.append(
            JobSummary(
                job_id=job_id,
                started_at=started_at,
                total=len(rows),
                completed=completed,
                failed=failed,
                in_flight=in_flight,
                status=_derive_job_status(statuses),
            )
        )

    summaries.sort(key=lambda s: s.started_at, reverse=True)
    return summaries[:limit]


@router.get("/job/{job_id}", response_model=list[UploadResponse])
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Get the uploads belonging to a specific job, ordered by created_at ASC.

    Returns the rows themselves (including sub-stage error columns) so the
    frontend can reconstruct the timeline of a finished job on cold load.
    """
    uploads = (
        db.query(Upload)
        .filter(Upload.job_id == job_id)
        .order_by(Upload.created_at.asc())
        .all()
    )
    if not uploads:
        raise HTTPException(status_code=404, detail="Job not found")

    # Pre-load channels for the rows so we can derive channel_has_default_comment
    channel_ids = {u.channel_id for u in uploads}
    channels_by_id: dict[int, Channel] = {
        c.id: c
        for c in db.query(Channel).filter(Channel.id.in_(channel_ids)).all()
    }

    results: list[UploadResponse] = []
    for u in uploads:
        ch = channels_by_id.get(u.channel_id)
        has_default = bool(ch and ch.default_comment and ch.default_comment.strip())
        item = UploadResponse.model_validate(u)
        item.channel_has_default_comment = has_default
        results.append(item)
    return results


@router.get("/video-status/{upload_id}")
def get_video_processing_status(upload_id: int, db: Session = Depends(get_db)):
    """Get YouTube processing status for an uploaded video."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload or not upload.youtube_video_id:
        raise HTTPException(status_code=404, detail="Upload not found or not yet uploaded")

    channel = db.query(Channel).filter(Channel.id == upload.channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    account = db.query(Account).filter(Account.id == channel.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    from backend.services.oauth_service import oauth_service
    creds = oauth_service.load_credentials(account.token_path)
    if not creds:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    yt_service = oauth_service.get_youtube_service(creds)
    status = youtube_service_instance.get_video_status(yt_service, upload.youtube_video_id)
    return status


@router.patch("/{upload_id}/youtube")
def update_youtube_video(upload_id: int, body: YoutubeEditRequest, db: Session = Depends(get_db)):
    """Edit title/description/tags/privacy of an already-uploaded YouTube video."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload or not upload.youtube_video_id:
        raise HTTPException(status_code=404, detail="Upload not found or not yet uploaded")

    channel = db.query(Channel).filter(Channel.id == upload.channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    account = db.query(Account).filter(Account.id == channel.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    from backend.services.oauth_service import oauth_service
    creds = oauth_service.load_credentials(account.token_path)
    if not creds:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    title = body.title if body.title is not None else upload.title
    description = body.description if body.description is not None else (upload.description or "")
    tags = body.tags if body.tags is not None else (upload.tags or "")
    privacy = body.privacy if body.privacy is not None else upload.privacy

    yt_service = oauth_service.get_youtube_service(creds)
    youtube_service_instance.update_video(
        yt_service, upload.youtube_video_id, title, description, tags, privacy
    )

    upload.title = title
    upload.description = description
    upload.tags = tags
    upload.privacy = privacy
    db.commit()
    db.refresh(upload)
    return upload


@router.post("/job/{job_id}/cancel")
def cancel_job(job_id: str):
    """Cancel a running upload job."""
    from backend.services.upload_manager import upload_manager
    upload_manager.cancel_job(job_id)
    return {"status": "cancelling"}
