# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import math
from dataclasses import dataclass

from sqlalchemy import false, or_
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
    page: int
    per_page: int



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


def combined_books(page=1, per_page=24, query_text="", source="all", media_type="", tag=""):
    """Return one deterministic recent-first window without loading either full library."""
    requested_page = max(int(page or 1), 1)
    per_page = max(1, min(int(per_page), 100))
    queries = {}
    if source in ("all", "calibre"):
        queries["calibre"] = _calibre_query(query_text, media_type, tag)
    if source in ("all", "external"):
        queries["external"] = _external_query(query_text, media_type, tag)
    if not queries:
        queries["external"] = _external_query(query_text, media_type, tag).filter(false())

    total = sum(query.order_by(None).count() for query in queries.values())
    pages = math.ceil(total / per_page) if total else 0
    effective_page = min(requested_page, pages) if pages else 1
    candidate_limit = effective_page * per_page
    candidates = []
    for source_name, query in queries.items():
        rows = (query.order_by(db.Books.timestamp.desc() if source_name == "calibre" else ExternalBook.created_at.desc())
                .order_by(db.Books.id.desc() if source_name == "calibre" else ExternalBook.id.desc())
                .limit(candidate_limit)
                .all())
        candidates.extend(
            (source_name, row[0], normalized_datetime(row[1])) for row in rows
        )
    candidates.sort(key=lambda item: (item[2], item[0], item[1]), reverse=True)
    offset = (effective_page - 1) * per_page
    selected = candidates[offset:offset + per_page]

    calibre_ids = [item[1] for item in selected if item[0] == "calibre"]
    external_ids = [item[1] for item in selected if item[0] == "external"]
    calibre_cards = _hydrate_calibre(calibre_ids)
    external_cards = _hydrate_external(external_ids)
    ordered_cards = [
        calibre_cards[item[1]] if item[0] == "calibre" else external_cards[item[1]]
        for item in selected
    ]
    return CatalogResult(ordered_cards, total, effective_page, per_page)


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
    books = combined_books(page=1, per_page=limit)
    movies = (ub.session.query(Movie)
              .order_by(Movie.created_at.desc(), Movie.id.desc())
              .limit(limit)
              .all())
    return books.cards, [movie_card(movie) for movie in movies], books.total, ub.session.query(Movie).count()
