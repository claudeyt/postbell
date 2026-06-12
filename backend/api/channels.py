from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.channel import Channel
from backend.models.channel_group import ChannelGroup
from backend.models.account import Account
from backend.schemas.channel import ChannelUpdate, ChannelResponse
from backend.schemas.channel_group import ReorderRequest

router = APIRouter(prefix="/api/channels", tags=["channels"])


class _MoveChannelRequest(BaseModel):
    group_id: int | None = None


# NOTE: /reorder is declared before /{channel_id} so FastAPI doesn't try to
# coerce the literal "reorder" into the int channel_id path param.
@router.patch("/reorder")
def reorder_channels(body: ReorderRequest, db: Session = Depends(get_db)):
    """Reorder channels within a container (group or ungrouped section).

    body.group_id scopes which container we're reordering inside (None =
    ungrouped). Sets channel.display_order = index in body.ids order. Caller
    is responsible for sending only IDs in that container.
    """
    for index, cid in enumerate(body.ids):
        db.query(Channel).filter(Channel.id == cid).update(
            {Channel.display_order: index}
        )
    db.commit()
    return {"updated": len(body.ids)}


@router.patch("/{channel_id}/group", response_model=ChannelResponse)
def move_channel_to_group(
    channel_id: int, body: _MoveChannelRequest, db: Session = Depends(get_db)
):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Channel not found")
    if body.group_id is not None:
        group = (
            db.query(ChannelGroup).filter(ChannelGroup.id == body.group_id).first()
        )
        if not group:
            raise HTTPException(404, "Group not found")
    ch.group_id = body.group_id
    db.commit()
    db.refresh(ch)
    return ch


@router.get("", response_model=list[ChannelResponse])
def list_channels(db: Session = Depends(get_db)):
    """List all channels across all accounts."""
    return db.query(Channel).all()


@router.get("/by-language")
def channels_by_language(db: Session = Depends(get_db)):
    """List channels grouped by language code."""
    channels = db.query(Channel).filter(Channel.is_active == True).all()  # noqa: E712
    grouped: dict[str, list] = {}
    for ch in channels:
        lang = ch.language_code or "unset"
        if lang not in grouped:
            grouped[lang] = []
        grouped[lang].append(ChannelResponse.model_validate(ch).model_dump())
    return grouped


# NOTE: /auto-detect-languages is declared BEFORE /{channel_id} routes so
# FastAPI matches the literal path first instead of trying to coerce
# "auto-detect-languages" into the int channel_id path param.
@router.post("/auto-detect-languages")
def auto_detect_languages(db: Session = Depends(get_db)):
    """Detect language for all channels without a language set.

    Iterates over channels where language_code IS NULL and runs the language
    service detection cascade (suffix -> mention -> keyword -> gemini) on each
    channel_name. Only writes a code that is in the canonical LANGUAGE_SUFFIXES
    set. Channels that already have a language_code are left untouched and
    counted in skipped_already_set.
    """
    from backend.services.language_service import language_service, LANGUAGE_SUFFIXES

    # "Unset" in this codebase means language_code IS NULL OR == "" (the
    # column default is "" and is NOT NULL per the model).
    candidates = db.query(Channel).filter(
        (Channel.language_code == "") | (Channel.language_code.is_(None))
    ).all()
    total_skipped_already_set = (
        db.query(Channel)
        .filter(Channel.language_code.isnot(None))
        .filter(Channel.language_code != "")
        .count()
    )

    results = []
    updated = 0
    skipped_unknown = 0

    for ch in candidates:
        code, method = language_service.detect_language(ch.channel_name)
        if code and code in LANGUAGE_SUFFIXES:
            ch.language_code = code
            updated += 1
            results.append({
                "channel_id": ch.id,
                "channel_name": ch.channel_name,
                "detected_language": code,
                "method": method,
                "set": True,
            })
        else:
            skipped_unknown += 1
            results.append({
                "channel_id": ch.id,
                "channel_name": ch.channel_name,
                "detected_language": None,
                "method": method,
                "set": False,
            })

    db.commit()

    return {
        "updated": updated,
        "skipped_unknown": skipped_unknown,
        "skipped_already_set": total_skipped_already_set,
        "results": results,
    }


# NOTE: /pull-youtube-tags/all and /{channel_id}/pull-youtube-tags are declared
# BEFORE the generic /{channel_id} PATCH route so FastAPI matches the literal
# path segment first instead of trying to coerce "pull-youtube-tags" into the
# int channel_id path param. /pull-youtube-tags/all is declared first because
# its first segment is a literal — must precede the /{channel_id}/... route so
# FastAPI does not try to coerce "pull-youtube-tags" into channel_id.
@router.post("/pull-youtube-tags/all")
def pull_youtube_tags_for_all(db: Session = Depends(get_db)):
    from backend.services.oauth_service import oauth_service
    from backend.services.quota_service import quota_service
    import shlex

    channels = db.query(Channel).all()
    updated = 0
    failed = 0
    results = []
    for ch in channels:
        try:
            acc = db.query(Account).filter(Account.id == ch.account_id).first()
            if not acc:
                failed += 1
                results.append({"channel_id": ch.id, "channel_name": ch.channel_name, "ok": False, "error": "no account"})
                continue
            creds = oauth_service.load_credentials(acc.token_path)
            if not creds:
                failed += 1
                results.append({"channel_id": ch.id, "channel_name": ch.channel_name, "ok": False, "error": "no credentials"})
                continue
            yt = oauth_service.get_youtube_service(creds)
            resp = yt.channels().list(part="brandingSettings", id=ch.channel_id).execute()
            items = resp.get("items", [])
            if not items:
                failed += 1
                results.append({"channel_id": ch.id, "channel_name": ch.channel_name, "ok": False, "error": "channel not found on YouTube"})
                continue
            branding = items[0].get("brandingSettings", {}).get("channel", {})
            raw_keywords = branding.get("keywords", "") or ""
            try:
                tags = shlex.split(raw_keywords)
            except ValueError:
                tags = raw_keywords.split()
            ch.default_tags = ",".join(tags) if tags else None
            updated += 1
            results.append({"channel_id": ch.id, "channel_name": ch.channel_name, "ok": True, "tag_count": len(tags)})
            try:
                quota_service.record_usage(project_id=acc.project_id, units=1, db=db)
            except Exception:
                pass
        except Exception as exc:
            failed += 1
            results.append({"channel_id": ch.id, "channel_name": ch.channel_name, "ok": False, "error": str(exc)})
    db.commit()
    return {"updated": updated, "failed": failed, "results": results}


@router.post("/{channel_id}/pull-youtube-tags", response_model=ChannelResponse)
def pull_youtube_tags(channel_id: int, db: Session = Depends(get_db)):
    from backend.services.oauth_service import oauth_service
    from backend.services.quota_service import quota_service

    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Channel not found")

    acc = db.query(Account).filter(Account.id == ch.account_id).first()
    if not acc:
        raise HTTPException(404, "Account not found")

    creds = oauth_service.load_credentials(acc.token_path)
    if not creds:
        raise HTTPException(401, "No valid credentials")

    yt = oauth_service.get_youtube_service(creds)
    resp = yt.channels().list(part="brandingSettings", id=ch.channel_id).execute()
    items = resp.get("items", [])
    if not items:
        raise HTTPException(404, "Channel not found on YouTube")

    branding = items[0].get("brandingSettings", {}).get("channel", {})
    raw_keywords = branding.get("keywords", "") or ""
    # YouTube returns keywords as a space-separated string with quoted tags
    # for multi-word ones, e.g. '"recap de anime" anime "anime recap"'.
    # Normalize to a comma-separated list.
    import shlex
    try:
        tags = shlex.split(raw_keywords)
    except ValueError:
        # If quoting is malformed, fall back to simple split
        tags = raw_keywords.split()
    ch.default_tags = ",".join(tags) if tags else None
    db.commit()
    db.refresh(ch)

    # Quota: 1 unit for channels.list
    try:
        quota_service.record_usage(project_id=acc.project_id, units=1, db=db)
    except Exception:
        pass

    return ch


@router.patch("/{channel_id}", response_model=ChannelResponse)
def update_channel(channel_id: int, update: ChannelUpdate, db: Session = Depends(get_db)):
    """Update channel language, alias, or active status."""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if update.language_code is not None:
        channel.language_code = update.language_code
    if update.alias is not None:
        channel.alias = update.alias
    if update.default_description is not None:
        channel.default_description = update.default_description
    if update.default_comment is not None:
        channel.default_comment = update.default_comment
    if "default_tags" in update.model_fields_set:
        channel.default_tags = update.default_tags
    if update.is_active is not None:
        channel.is_active = update.is_active
    # custom_schedule_time: distinguish "absent" (no change) from "null" (clear)
    if "custom_schedule_time" in update.model_fields_set:
        channel.custom_schedule_time = update.custom_schedule_time

    db.commit()
    db.refresh(channel)
    return channel


@router.post("/{account_id}/sync")
def sync_channels(account_id: int, db: Session = Depends(get_db)):
    """Re-fetch channels from YouTube for an account."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    from backend.services.oauth_service import oauth_service

    creds = oauth_service.load_credentials(account.token_path)
    if not creds:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    discovered = oauth_service.discover_channels(creds)
    new_channels = []
    for ch_data in discovered:
        existing = db.query(Channel).filter(Channel.channel_id == ch_data["channel_id"]).first()
        if not existing:
            channel = Channel(
                account_id=account.id,
                channel_id=ch_data["channel_id"],
                channel_name=ch_data["channel_name"],
                thumbnail_url=ch_data.get("thumbnail_url"),
                language_code="",
            )
            db.add(channel)
            new_channels.append(ch_data["channel_name"])
    db.commit()
    return {"synced": len(new_channels), "new_channels": new_channels}
