import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database.database import get_db
from app.config.log.log_config import get_logger
from app.core.dependencies import get_current_user, require_admin
from app.models.client_error_report import ClientErrorReportRecord
from app.models.user import User
from app.schemas.client_error import ClientErrorReport
from app.schemas.client_error import ClientErrorListResponse, ClientErrorRecordResponse

router = APIRouter(prefix="/client-errors", tags=["client-errors"])
logger = get_logger("client_errors_router")
_dedupe_lock = Lock()
_recent_reports: dict[str, float] = {}
_dedupe_window_seconds = max(
    1,
    int(os.getenv("CLIENT_ERROR_DEDUPE_WINDOW_SECONDS", "60")),
)
_dedupe_cache_size = max(
    100,
    int(os.getenv("CLIENT_ERROR_DEDUPE_CACHE_SIZE", "2000")),
)
_client_error_log_dir = Path(os.getenv("CLIENT_ERROR_LOG_DIR", "./logs/client-errors"))


def _trim(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _build_fingerprint(
    payload: ClientErrorReport, sanitized_metadata: dict[str, str]
) -> str:
    if payload.fingerprint:
        return payload.fingerprint

    raw = "|".join(
        [
            payload.app,
            payload.source,
            payload.message,
            payload.route or "",
            payload.url or "",
            payload.stack or "",
            json.dumps(sanitized_metadata, sort_keys=True),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:64]


def _register_report(fingerprint: str) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    with _dedupe_lock:
        expired = [
            key
            for key, timestamp in _recent_reports.items()
            if now - timestamp > _dedupe_window_seconds
        ]
        for key in expired:
            _recent_reports.pop(key, None)

        last_seen = _recent_reports.get(fingerprint)
        _recent_reports[fingerprint] = now

        if len(_recent_reports) > _dedupe_cache_size:
            oldest_key = min(_recent_reports, key=_recent_reports.get)
            _recent_reports.pop(oldest_key, None)

    return last_seen is None or now - last_seen > _dedupe_window_seconds


def _persist_report(record: dict[str, object]) -> None:
    _client_error_log_dir.mkdir(parents=True, exist_ok=True)
    filename = datetime.now(timezone.utc).strftime("client-errors-%Y-%m-%d.jsonl")
    filepath = _client_error_log_dir / filename
    with filepath.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _to_response_model(record: ClientErrorReportRecord) -> ClientErrorRecordResponse:
    metadata: dict[str, str] = {}
    if record.metadata_json:
        try:
            metadata = json.loads(record.metadata_json)
        except json.JSONDecodeError:
            metadata = {"raw": record.metadata_json[:500]}

    return ClientErrorRecordResponse(
        id=record.id,
        app=record.app,
        source=record.source,
        message=record.message,
        fingerprint=record.fingerprint,
        stack=record.stack,
        url=record.url,
        route=record.route,
        userAgent=record.user_agent,
        clientIp=record.client_ip,
        metadata=metadata,
        deduplicated=record.deduplicated,
        createdAt=record.created_at,
    )


def _log_client_record(record: dict[str, object]) -> None:
    level = str(record.get("metadata", {}).get("level", "error")).lower()
    message = (
        "Client event reported | level=%s app=%s source=%s route=%s url=%s ip=%s "
        "fingerprint=%s deduplicated=%s user_agent=%s message=%s metadata=%s stack=%s"
    )
    args = (
        level,
        record.get("app"),
        record.get("source"),
        record.get("route"),
        record.get("url"),
        record.get("clientIp"),
        record.get("fingerprint"),
        record.get("deduplicated"),
        record.get("userAgent"),
        record.get("message"),
        record.get("metadata"),
        record.get("stack"),
    )

    if level in {"trace", "debug"}:
        logger.debug(message, *args)
    elif level in {"log", "info"}:
        logger.info(message, *args)
    elif level == "warn":
        logger.warning(message, *args)
    else:
        logger.error(message, *args)


@router.post("")
async def log_client_error(
    payload: ClientErrorReport,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    sanitized_metadata = {
        key: str(value)[:500] for key, value in payload.metadata.items()
    }
    fingerprint = _build_fingerprint(payload, sanitized_metadata)
    is_new_report = _register_report(fingerprint)
    record = {
        "receivedAt": datetime.now(timezone.utc).isoformat(),
        "app": payload.app,
        "source": payload.source,
        "message": _trim(payload.message, 2000),
        "stack": _trim(payload.stack, 8000),
        "url": _trim(payload.url, 2000),
        "route": _trim(payload.route, 512),
        "userAgent": _trim(payload.userAgent, 512),
        "clientIp": client_ip,
        "fingerprint": fingerprint,
        "metadata": sanitized_metadata,
        "deduplicated": not is_new_report,
    }

    if is_new_report:
        try:
            _persist_report(record)
        except OSError as exc:
            logger.exception("Failed to persist client error report: %s", str(exc))

    db_record = ClientErrorReportRecord(
        app=payload.app,
        source=payload.source,
        message=_trim(payload.message, 2000) or "Unknown error",
        fingerprint=fingerprint,
        stack=_trim(payload.stack, 8000),
        url=_trim(payload.url, 2000),
        route=_trim(payload.route, 512),
        user_agent=_trim(payload.userAgent, 512),
        client_ip=client_ip,
        metadata_json=json.dumps(sanitized_metadata, ensure_ascii=True),
        deduplicated=not is_new_report,
    )
    db.add(db_record)
    await db.flush()

    _log_client_record(record)
    return {
        "status": "logged" if is_new_report else "duplicate",
        "fingerprint": fingerprint,
        "id": db_record.id,
    }


@router.get("", response_model=ClientErrorListResponse)
async def get_client_errors(
    app: str | None = Query(default=None, max_length=64),
    source: str | None = Query(default=None, max_length=128),
    route: str | None = Query(default=None, max_length=512),
    fingerprint: str | None = Query(default=None, max_length=128),
    deduplicated: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_admin(current_user)

    conditions = []
    if app:
        conditions.append(ClientErrorReportRecord.app == app)
    if source:
        conditions.append(ClientErrorReportRecord.source == source)
    if route:
        conditions.append(ClientErrorReportRecord.route == route)
    if fingerprint:
        conditions.append(ClientErrorReportRecord.fingerprint == fingerprint)
    if deduplicated is not None:
        conditions.append(ClientErrorReportRecord.deduplicated == deduplicated)

    total_stmt = select(func.count()).select_from(ClientErrorReportRecord)
    data_stmt = select(ClientErrorReportRecord)

    if conditions:
        total_stmt = total_stmt.where(*conditions)
        data_stmt = data_stmt.where(*conditions)

    total = await db.scalar(total_stmt)
    result = await db.execute(
        data_stmt.order_by(desc(ClientErrorReportRecord.created_at))
        .offset(offset)
        .limit(limit)
    )
    items = [_to_response_model(record) for record in result.scalars().all()]

    return ClientErrorListResponse(
        items=items,
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )
