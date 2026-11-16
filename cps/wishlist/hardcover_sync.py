# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Import a Hardcover reading shelf into the wishlist."""

import os

import requests

from .. import config, logger, ub
from ..metadata_provider.hardcover import Hardcover
from . import service
from .models import MediaRequest

log = logger.create()

STATUS_IDS = {
    "want-to-read": 1,
    "currently-reading": 2,
    "read": 3,
    "did-not-finish": 4,
}
SHELF_QUERY = (
    "query ShelfBooks($status_id: Int!) { "
    "me { user_books(where: {status_id: {_eq: $status_id}}) { book { id title } } } "
    "}"
)


def _token(user=None):
    return (
        getattr(user, "hardcover_token", None)
        or getattr(config, "config_hardcover_token", None)
        or os.getenv("HARDCOVER_TOKEN")
    )


def fetch_shelf_books(token, status_id, timeout=30):
    headers = Hardcover.HEADERS.copy()
    headers["Authorization"] = "Bearer %s" % str(token).replace("Bearer ", "")
    response = requests.post(
        Hardcover.BASE_URL,
        json={"query": SHELF_QUERY, "variables": {"status_id": int(status_id)}},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ValueError("Hardcover returned an error while reading the shelf.")
    data = payload.get("data") or {}
    me = data.get("me") or []
    if isinstance(me, list):
        me = me[0] if me else {}
    if not isinstance(me, dict):
        return []
    books = []
    for row in me.get("user_books") or []:
        book = row.get("book") if isinstance(row, dict) else None
        if not isinstance(book, dict):
            continue
        try:
            book_id = int(book.get("id"))
        except (TypeError, ValueError):
            continue
        title = str(book.get("title") or "").strip()
        if book_id and title:
            books.append({"id": book_id, "title": title})
    return books


def _already_requested(provider, provider_id):
    return (
        ub.session.query(MediaRequest)
        .filter(MediaRequest.metadata_provider == provider)
        .filter(MediaRequest.metadata_id == str(provider_id))
        .first()
        is not None
    )


def _owned(book_id, title):
    try:
        from ..media.library_check import annotate_books

        record = {
            "id": str(book_id),
            "title": title,
            "authors": [],
            "identifiers": {"hardcover": str(book_id)},
            "source": {"id": "hardcover"},
        }
        return bool(annotate_books([record])[0].get("owned"))
    except Exception:
        return False


def sync_user(user, shelf="want-to-read", content_type="book", limit=100):
    token = _token(user)
    if not token:
        raise ValueError("Set a Hardcover token on your account first.")
    status_id = STATUS_IDS.get(shelf, 1)
    content_type = content_type if content_type in ("book", "audiobook") else "book"
    books = fetch_shelf_books(token, status_id)[: max(1, int(limit))]
    created = 0
    skipped = 0
    for book in books:
        if _already_requested("hardcover", book["id"]) or _owned(book["id"], book["title"]):
            skipped += 1
            continue
        entry, was_created = service.create_request(
            user.id,
            content_type,
            book["title"],
            metadata_provider="hardcover",
            metadata_id=str(book["id"]),
            identifiers={"hardcover": str(book["id"])},
            note="Imported from Hardcover.",
        )
        if was_created:
            created += 1
        else:
            skipped += 1
    return {"total": len(books), "created": created, "skipped": skipped}


def sync_all_users(shelf=None, content_type=None):
    shelf = shelf or os.getenv("HARDCOVER_SYNC_SHELF", "want-to-read")
    content_type = content_type or os.getenv("HARDCOVER_SYNC_CONTENT_TYPE", "book")
    users = [
        user
        for user in ub.session.query(ub.User).all()
        if getattr(user, "hardcover_token", None)
    ]
    if not users:
        admin = next(
            (
                user
                for user in ub.session.query(ub.User).order_by(ub.User.id).all()
                if user.role_admin() and _token(user)
            ),
            None,
        )
        if admin is not None:
            users = [admin]
    results = []
    for user in users:
        try:
            results.append(sync_user(user, shelf, content_type))
        except Exception as exc:
            log.warning("Hardcover wishlist sync failed for %s: %s", user.name, exc)
    return results
