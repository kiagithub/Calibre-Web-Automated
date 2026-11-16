# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wishlist request lifecycle and permission helpers."""

from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from .. import logger, ub
from ..media.permissions import media_permissions
from .models import CONTENT_TYPES, OPEN_STATUSES, STATUSES, MediaRequest

log = logger.create()

MAX_PENDING_REQUESTS = 20


class RequestError(ValueError):
    pass


def _commit():
    try:
        ub.session.commit()
        return True
    except SQLAlchemyError as exc:
        ub.session.rollback()
        log.error("Could not save wishlist change: %s", exc)
        return False


def can_moderate(user):
    return media_permissions(user)["can_edit_media"]


def visible_requests(user, status="", content_type=""):
    query = ub.session.query(MediaRequest)
    if not can_moderate(user):
        query = query.filter(MediaRequest.user_id == getattr(user, "id", None))
    if status in STATUSES:
        query = query.filter(MediaRequest.status == status)
    if content_type in CONTENT_TYPES:
        query = query.filter(MediaRequest.content_type == content_type)
    return query.order_by(MediaRequest.created_at.desc(), MediaRequest.id.desc())


def pending_count(user_id):
    return (
        ub.session.query(MediaRequest)
        .filter(MediaRequest.user_id == user_id)
        .filter(MediaRequest.status.in_(OPEN_STATUSES))
        .count()
    )


def create_request(
    user_id,
    content_type,
    title,
    *,
    authors=None,
    director="",
    identifiers=None,
    metadata_provider="",
    metadata_id="",
    metadata_url="",
    cover_url="",
    note="",
    status="pending",
):
    content_type = str(content_type or "").strip().lower()
    if content_type not in CONTENT_TYPES:
        raise RequestError("Select a valid request type.")
    title = " ".join(str(title or "").split())[:300]
    if not title:
        raise RequestError("Title is required.")
    if pending_count(user_id) >= MAX_PENDING_REQUESTS:
        raise RequestError(
            f"You already have {MAX_PENDING_REQUESTS} open requests. "
            "Wait for one to be reviewed before adding another."
        )
    existing = (
        ub.session.query(MediaRequest)
        .filter(MediaRequest.user_id == user_id)
        .filter(MediaRequest.content_type == content_type)
        .filter(MediaRequest.status.in_(OPEN_STATUSES))
        .filter(MediaRequest.title == title)
        .first()
    )
    if existing is not None:
        return existing, False
    request = MediaRequest(
        user_id=user_id,
        content_type=content_type,
        status=status if status in STATUSES else "pending",
        title=title,
        director=" ".join(str(director or "").split())[:300],
        metadata_provider=str(metadata_provider or "").strip()[:50],
        metadata_id=str(metadata_id or "").strip()[:255],
        metadata_url=str(metadata_url or "").strip()[:1000],
        cover_url=str(cover_url or "").strip()[:2000],
        note=str(note or "").strip()[:10000],
    )
    request.authors = authors or []
    request.identifiers = identifiers or {}
    ub.session.add(request)
    if not _commit():
        raise RequestError("The request could not be saved. Please try again.")
    return request, True


def approve_request(request, actor_id, note=""):
    if request.status not in ("pending", "rejected"):
        raise RequestError("Only pending or rejected requests can be approved.")
    request.status = "approved"
    request.decided_by = actor_id
    request.decided_at = datetime.now(timezone.utc)
    request.admin_note = str(note or "").strip()[:10000]
    if not _commit():
        raise RequestError("The request could not be approved.")


def reject_request(request, actor_id, note=""):
    if request.status not in OPEN_STATUSES:
        raise RequestError("Only open requests can be rejected.")
    request.status = "rejected"
    request.decided_by = actor_id
    request.decided_at = datetime.now(timezone.utc)
    request.admin_note = str(note or "").strip()[:10000]
    if not _commit():
        raise RequestError("The request could not be rejected.")


def cancel_request(request, actor_id):
    if request.status not in OPEN_STATUSES:
        raise RequestError("Only open requests can be cancelled.")
    if request.user_id != actor_id and not can_moderate(
        ub.session.get(ub.User, actor_id)
    ):
        raise RequestError("You can only cancel your own requests.")
    request.status = "cancelled"
    request.decided_by = actor_id
    request.decided_at = datetime.now(timezone.utc)
    if not _commit():
        raise RequestError("The request could not be cancelled.")


def reopen_request(request, actor_id):
    if request.status not in ("rejected", "fulfilled"):
        raise RequestError("Only rejected or fulfilled requests can be reopened.")
    request.status = "pending"
    request.decided_by = None
    request.decided_at = None
    request.fulfilled_external_book_id = None
    request.fulfilled_movie_id = None
    if not _commit():
        raise RequestError("The request could not be reopened.")


def fulfill_request(request, actor_id, *, external_book_id=None, movie_id=None):
    if request.status not in OPEN_STATUSES:
        raise RequestError("Only open requests can be fulfilled.")
    request.status = "fulfilled"
    request.decided_by = actor_id
    request.decided_at = datetime.now(timezone.utc)
    request.fulfilled_external_book_id = external_book_id
    request.fulfilled_movie_id = movie_id
    if not _commit():
        raise RequestError("The request could not be marked fulfilled.")
