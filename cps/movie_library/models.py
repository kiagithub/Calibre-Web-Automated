# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from ..ub import Base


def utc_now():
    return datetime.now(timezone.utc)


class Movie(Base):
    """One physical movie edition/copy, including its online metadata."""

    __tablename__ = "movie"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False, index=True)
    original_title = Column(String(300), default="")
    overview = Column(Text, default="")
    release_date = Column(String(10), default="", index=True)
    runtime = Column(Integer)
    director = Column(String(500), default="")
    cast_members = Column(Text, default="")
    genres = Column(String(500), default="")
    content_rating = Column(String(20), default="")
    tmdb_rating = Column(Float)
    personal_rating = Column(Integer)
    tmdb_id = Column(Integer, index=True)
    imdb_id = Column(String(20), default="")

    media_format = Column(String(40), nullable=False, default="Blu-ray", index=True)
    location = Column(String(200), default="", index=True)
    barcode = Column(String(64), default="")
    edition = Column(String(200), default="")
    condition = Column(String(40), default="Good")
    date_acquired = Column(String(10), default="")
    is_watched = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, default="")

    poster_filename = Column(String(100), default="")
    metadata_updated_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    @property
    def year(self):
        return self.release_date[:4] if self.release_date else ""

    @property
    def genre_list(self):
        return [value.strip() for value in (self.genres or "").split(",") if value.strip()]

    @property
    def cast_list(self):
        return [value.strip() for value in (self.cast_members or "").split(",") if value.strip()]

    def __repr__(self):
        return f"<Movie {self.id}: {self.title!r} ({self.media_format})>"
