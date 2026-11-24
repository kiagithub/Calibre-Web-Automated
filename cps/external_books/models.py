# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship, validates

from ..ub import Base

MEDIA_TYPES = ("physical", "kindle", "other_digital", "audiobook")
AUDIO_FORMATS = ("M4B", "MP3", "Other")
CONDITIONS = ("New", "Like new", "Good", "Fair", "Poor")


def utc_now():
    return datetime.now(timezone.utc)


def clean_tag_name(value):
    return " ".join(unicodedata.normalize("NFKC", value or "").split())


def normalize_tag_name(value):
    """Return a stable comparison form without changing the display name."""
    return clean_tag_name(value).casefold()


def _string_list(value):
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


class ExternalBook(Base):
    """One shared, owned book edition/copy with no Calibre file dependency."""

    __tablename__ = "external_book"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False, index=True)
    authors_json = Column(Text, nullable=False, default="[]")
    description = Column(Text, nullable=False, default="")
    publisher = Column(String(300), nullable=False, default="")
    published_date = Column(String(10), default="", index=True)
    series = Column(String(300), nullable=False, default="", index=True)
    series_index = Column(String(20), nullable=False, default="")
    languages_json = Column(Text, nullable=False, default="[]")
    page_count = Column(Integer)

    media_type = Column(String(20), nullable=False, default="physical", index=True)
    narrator = Column(String(300), nullable=False, default="")
    duration_minutes = Column(Integer)
    abridged = Column(Boolean, nullable=False, default=False)
    audio_format = Column(String(20), nullable=False, default="")
    binding = Column(String(40), nullable=False, default="")
    edition = Column(String(200), nullable=False, default="")
    location = Column(String(200), nullable=False, default="", index=True)
    condition = Column(String(40), nullable=False, default="")
    date_acquired = Column(String(10), nullable=False, default="")
    personal_rating = Column(Integer)
    notes = Column(Text, nullable=False, default="")

    isbn_10 = Column(String(20), default="", index=True)
    isbn_13 = Column(String(20), default="", index=True)
    asin = Column(String(20), default="", index=True)
    metadata_provider = Column(String(50), nullable=False, default="")
    metadata_id = Column(String(255), default="", index=True)
    metadata_url = Column(String(1000), nullable=False, default="")

    cover_filename = Column(String(100), nullable=False, default="")
    metadata_updated_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    tags = relationship(
        "ExternalBookTag",
        back_populates="book",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExternalBookTag.name",
    )

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
    def languages(self):
        try:
            return _string_list(json.loads(self.languages_json or "[]"))
        except (TypeError, ValueError):
            return []

    @languages.setter
    def languages(self, value):
        self.languages_json = json.dumps(_string_list(value), ensure_ascii=False)

    @property
    def tag_names(self):
        return [tag.name for tag in self.tags]

    @property
    def content_type(self):
        return "audiobook" if self.media_type == "audiobook" else "book"

    def __repr__(self):
        return f"<ExternalBook {self.id}: {self.title!r} ({self.media_type})>"


class ExternalBookTag(Base):
    __tablename__ = "external_book_tag"
    __table_args__ = (
        UniqueConstraint("external_book_id", "normalized_name", name="uq_external_book_tag_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_book_id = Column(
        Integer, ForeignKey("external_book.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(100), nullable=False)
    normalized_name = Column(String(100), nullable=False, index=True)
    book = relationship("ExternalBook", back_populates="tags")

    @validates("name")
    def _clean_and_normalize_name(self, _key, value):
        name = clean_tag_name(value)
        if not name or len(name) > 100:
            raise ValueError("Tag names must contain 1 to 100 characters.")
        self.normalized_name = normalize_tag_name(name)
        return name

    def __repr__(self):
        return f"<ExternalBookTag {self.name!r}>"
