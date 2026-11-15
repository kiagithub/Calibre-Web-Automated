# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass
from datetime import datetime, timezone

from flask import url_for

MEDIA_TYPE_LABELS = {
    "physical": "Physical",
    "kindle": "Kindle",
    "other_digital": "Other digital",
}


@dataclass(frozen=True)
class CatalogCard:
    source: str
    id: int
    title: str
    byline: str
    cover_url: str
    detail_url: str
    badge: str
    location: str
    state: str = ""


def normalized_datetime(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def calibre_card(book):
    book = getattr(book, "Books", book)
    authors = ", ".join(author.name for author in book.authors)
    return CatalogCard(
        source="calibre",
        id=book.id,
        title=book.title,
        byline=authors,
        cover_url=url_for("web.get_cover", book_id=book.id, resolution="og"),
        detail_url=url_for("web.show_book", book_id=book.id),
        badge="Calibre",
        location="",
    )


def external_book_card(book):
    return CatalogCard(
        source="external",
        id=book.id,
        title=book.title,
        byline=", ".join(book.authors),
        cover_url=(url_for("external_books.cover", book_id=book.id) if book.cover_filename
                   else url_for("static", filename="generic_cover.svg")),
        detail_url=url_for("external_books.detail", book_id=book.id),
        badge=MEDIA_TYPE_LABELS.get(book.media_type, book.media_type),
        location=book.location,
    )


def movie_card(movie):
    byline = movie.director or ""
    if movie.year:
        byline = f"{byline} · {movie.year}" if byline else movie.year
    return CatalogCard(
        source="movie",
        id=movie.id,
        title=movie.title,
        byline=byline,
        cover_url=(url_for("movies.poster", movie_id=movie.id) if movie.poster_filename
                   else url_for("static", filename="generic_cover.svg")),
        detail_url=url_for("movies.detail", movie_id=movie.id),
        badge=movie.media_format,
        location=movie.location,
        state="Watched" if movie.is_watched else "",
    )
