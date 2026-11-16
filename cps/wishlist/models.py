# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wishlist and acquisition requests for books, audiobooks, and movies."""

import json
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..ub import Base

CONTENT_TYPES = ("book", "audiobook", "movie")
STATUSES = ("pending", "approved", "rejected", "fulfilled", "cancelled")
OPEN_STATUSES = ("pending", "approved")


def utc_now():
    return datetime.now(timezone.utc)


def _string_list(value):
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


class MediaRequest(Base):
    __tablename__ = "media_request"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_type = Column(String(20), nullable=False, default="book", index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    title = Column(String(300), nullable=False)
    authors_json = Column(Text, nullable=False, default="[]")
    director = Column(String(300), nullable=False, default="")
    identifiers_json = Column(Text, nullable=False, default="{}")
    metadata_provider = Column(String(50), nullable=False, default="")
    metadata_id = Column(String(255), default="")
    metadata_url = Column(String(1000), nullable=False, default="")
    cover_url = Column(String(2000), nullable=False, default="")
    note = Column(Text, nullable=False, default="")
    admin_note = Column(Text, nullable=False, default="")
    decided_by = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime)
    fulfilled_external_book_id = Column(
        Integer, ForeignKey("external_book.id", ondelete="SET NULL"), nullable=True
    )
    fulfilled_movie_id = Column(
        Integer, ForeignKey("movie.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    requester = relationship("User", foreign_keys=[user_id])
    decider = relationship("User", foreign_keys=[decided_by])

    @property
    def authors(self):
        try:
            return _string_list(json.loads(self.authors_json or "[]"))
        except (TypeError, ValueError):
            return []

    @authors.setter
    def authors(self, value):
        self.authors_json = json.dumps(_string_list(value), ensure_ascii=False)

    @property
    def identifiers(self):
        try:
            value = json.loads(self.identifiers_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @identifiers.setter
    def identifiers(self, value):
        self.identifiers_json = json.dumps(
            {str(key): str(item) for key, item in (value or {}).items() if item},
            ensure_ascii=False,
        )

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES

    def __repr__(self):
        return f"<MediaRequest {self.id}: {self.title!r} ({self.status})>"
