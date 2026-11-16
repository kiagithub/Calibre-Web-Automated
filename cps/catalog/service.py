# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, false, or_
from sqlalchemy.orm import noload, raiseload, selectinload

from .. import calibre_db, db, ub
from ..external_books.models import ExternalBook, ExternalBookTag, clean_tag_name, normalize_tag_name
from ..external_books.query import filtered_external_books
from ..media.queries import escaped_like
from ..movie_library.models import Movie
from .read_models import (
    calibre_card,
    external_book_card,
    movie_card,
    normalized_datetime,
)


@dataclass
class CatalogResult:
    cards: list
    total: int
    per_page: int
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    has_next: bool = False
    has_prev: bool = False


CURSOR_MAX_LENGTH = 500


def encode_cursor(timestamp, source, item_id):
    payload = f"{normalized_datetime(timestamp).isoformat()}|{source}|{int(item_id)}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(value):
    """Decode a keyset cursor, returning None for missing or malformed input."""
    if not value or len(value) > CURSOR_MAX_LENGTH:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        timestamp, source, item_id = payload.split("|")
        if source not in ("calibre", "external"):
            return None
        return normalized_datetime(datetime.fromisoformat(timestamp)), source, int(item_id)
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        return None


def _cursor_for(item):
    return encode_cursor(item[2], item[0], item[1])


def _cursor_sql_time(cursor_time):
    # SQLite stores DateTime values without a timezone; compare in UTC-naive form.
    return cursor_time.replace(tzinfo=None)


def _source_rows(source_name, query, cursor, direction, per_page):
    time_col = db.Books.timestamp if source_name == "calibre" else ExternalBook.created_at
    id_col = db.Books.id if source_name == "calibre" else ExternalBook.id
    if cursor is not None:
        cursor_time, cursor_source, cursor_id = cursor
        sql_time = _cursor_sql_time(cursor_time)
        if direction == "prev":
            if source_name == cursor_source:
                query = query.filter(or_(
                    time_col > sql_time,
                    and_(time_col == sql_time, id_col > cursor_id),
                ))
            elif source_name > cursor_source:
                query = query.filter(time_col >= sql_time)
            else:
                query = query.filter(time_col > sql_time)
            query = query.order_by(time_col.asc(), id_col.asc())
        else:
            if source_name == cursor_source:
                query = query.filter(or_(
                    time_col < sql_time,
                    and_(time_col == sql_time, id_col < cursor_id),
                ))
            elif source_name > cursor_source:
                query = query.filter(time_col < sql_time)
            else:
                query = query.filter(time_col <= sql_time)
            query = query.order_by(time_col.desc(), id_col.desc())
    else:
        query = query.order_by(time_col.desc(), id_col.desc())
    return [
        (source_name, row[0], normalized_datetime(row[1]))
        for row in query.limit(per_page + 1).all()
    ]


def _calibre_query(query_text, media_type, tag):
    query = calibre_db.session.query(db.Books.id, db.Books.timestamp).filter(calibre_db.common_filters())
    if media_type:
        return query.filter(false())
    if query_text:
        term = escaped_like(query_text)
        query = query.filter(or_(
            db.Books.title.ilike(term, escape="\\"),
            db.Books.author_sort.ilike(term, escape="\\"),
            db.Books.authors.any(db.Authors.name.ilike(term, escape="\\")),
            db.Books.series.any(db.Series.name.ilike(term, escape="\\")),
            db.Books.publishers.any(db.Publishers.name.ilike(term, escape="\\")),
            db.Books.identifiers.any(db.Identifiers.val.ilike(term, escape="\\")),
        ))
    if tag:
        exact_tag = clean_tag_name(tag).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(db.Books.tags.any(db.Tags.name.ilike(exact_tag, escape="\\")))
    return query


def _external_query(query_text, media_type, tag):
    return filtered_external_books(ub.session, query_text, media_type, tag).with_entities(
        ExternalBook.id, ExternalBook.created_at
    )


def _hydrate_calibre(ids):
    if not ids:
        return {}
    books = (calibre_db.session.query(db.Books)
             .filter(db.Books.id.in_(ids))
             .options(raiseload("*"), selectinload(db.Books.authors))
             .all())
    return {book.id: calibre_card(book) for book in books}


def _hydrate_external(ids):
    if not ids:
        return {}
    books = (ub.session.query(ExternalBook).filter(ExternalBook.id.in_(ids))
             .options(noload(ExternalBook.tags)).all())
    return {book.id: external_book_card(book) for book in books}


def combined_books(cursor=None, direction="next", per_page=24, query_text="", source="all", media_type="", tag=""):
    """Return one deterministic recent-first window using keyset pagination."""
    per_page = max(1, min(int(per_page), 100))
    direction = "prev" if direction == "prev" else "next"
    decoded = decode_cursor(cursor)
    if direction == "prev" and decoded is None:
        direction = "next"

    queries = {}
    if source in ("all", "calibre"):
        queries["calibre"] = _calibre_query(query_text, media_type, tag)
    if source in ("all", "external"):
        queries["external"] = _external_query(query_text, media_type, tag)
    if not queries:
        queries["external"] = _external_query(query_text, media_type, tag).filter(false())

    total = sum(query.order_by(None).count() for query in queries.values())
    candidates = []
    for source_name, query in queries.items():
        candidates.extend(_source_rows(source_name, query, decoded, direction, per_page))

    if direction == "prev":
        candidates.sort(key=lambda item: (item[2], item[0], item[1]))
        has_prev = len(candidates) > per_page
        selected = list(reversed(candidates[-per_page:]))
        has_next = bool(selected)
        next_cursor = _cursor_for(selected[-1]) if selected else None
        prev_cursor = _cursor_for(selected[0]) if has_prev and selected else None
    else:
        candidates.sort(key=lambda item: (item[2], item[0], item[1]), reverse=True)
        selected = candidates[:per_page]
        has_next = len(candidates) > per_page
        has_prev = decoded is not None and bool(selected)
        next_cursor = _cursor_for(selected[-1]) if has_next and selected else None
        prev_cursor = _cursor_for(selected[0]) if has_prev and selected else None
        if decoded is not None and not selected:
            # The cursor no longer maps to a row; let the user step back.
            prev_cursor = cursor
            has_prev = True

    calibre_ids = [item[1] for item in selected if item[0] == "calibre"]
    external_ids = [item[1] for item in selected if item[0] == "external"]
    calibre_cards = _hydrate_calibre(calibre_ids)
    external_cards = _hydrate_external(external_ids)
    ordered_cards = [
        calibre_cards[item[1]] if item[0] == "calibre" else external_cards[item[1]]
        for item in selected
    ]
    return CatalogResult(
        ordered_cards, total, per_page, next_cursor, prev_cursor, has_next, has_prev
    )


def available_tags():
    """Return display tags from visible Calibre books and external records."""
    names = {}
    external_rows = ub.session.query(ExternalBookTag.name).distinct().all()
    calibre_rows = (calibre_db.session.query(db.Tags.name)
                    .join(db.books_tags_link, db.Tags.id == db.books_tags_link.c.tag)
                    .join(db.Books, db.Books.id == db.books_tags_link.c.book)
                    .filter(calibre_db.common_filters())
                    .distinct().all())
    for row in [*external_rows, *calibre_rows]:
        name = clean_tag_name(row[0])
        if name:
            names.setdefault(normalize_tag_name(name), name)
    return sorted(names.values(), key=normalize_tag_name)


def recent_home(limit=12):
    books = combined_books(per_page=limit)
    movies = (ub.session.query(Movie)
              .order_by(Movie.created_at.desc(), Movie.id.desc())
              .limit(limit)
              .all())
    return books.cards, [movie_card(movie) for movie in movies], books.total, ub.session.query(Movie).count()
