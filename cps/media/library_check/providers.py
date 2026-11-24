# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read-only library indexes for ownership checks."""

import os
from urllib.parse import urlparse

import requests
from sqlalchemy import func
from sqlalchemy.orm import noload, selectinload

from ... import calibre_db, config, db, ub
from ...external_books.models import ExternalBook
from ...movie_library.models import Movie
from ..text_match import author_surname, clean_title_tokens, isbn_variants, significant_tokens
from .matcher import LibraryEntry, MovieEntry

_EXTERNAL_ID_TYPES = {
    "dnb-idn": "dnb",
    "google": "google",
    "goodreads": "goodreads",
    "hardcover-id": "hardcover",
    "olid": "openlibrary",
    "openlibrary": "openlibrary",
    "storygraph": "storygraph",
}
_ISBN_TYPES = {"isbn", "isbn10", "isbn-10", "isbn13", "isbn-13"}
_ASIN_TYPES = {"amazon", "asin", "mobi-asin"}


def personal_fingerprint():
    count, updated = (
        ub.session.query(func.count(ExternalBook.id), func.max(ExternalBook.updated_at)).one()
    )
    return int(count or 0), updated


def movie_fingerprint():
    count, updated = ub.session.query(func.count(Movie.id), func.max(Movie.updated_at)).one()
    return int(count or 0), updated


def _audiobookshelf_config():
    enabled = os.getenv("AUDIOBOOKSHELF_CHECK_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )
    url = os.getenv("AUDIOBOOKSHELF_URL", "").strip().rstrip("/")
    token = os.getenv("AUDIOBOOKSHELF_TOKEN", "").strip()
    library_ids = [
        value.strip()
        for value in os.getenv("AUDIOBOOKSHELF_LIBRARY_IDS", "").split(",")
        if value.strip()
    ]
    if not enabled or not url or not token:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return url, token, library_ids


def audiobookshelf_enabled():
    return _audiobookshelf_config() is not None


def audiobookshelf_entries():
    config = _audiobookshelf_config()
    if config is None:
        return []
    url, token, library_ids = config
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{url}/api/libraries", headers=headers, timeout=15)
    response.raise_for_status()
    payload = response.json()
    libraries = payload.get("libraries") if isinstance(payload, dict) else []
    if not isinstance(libraries, list):
        raise ValueError("Audiobookshelf returned an invalid library list.")
    selected = []
    for library in libraries:
        if not isinstance(library, dict) or not library.get("id"):
            continue
        if library_ids:
            if library["id"] in library_ids:
                selected.append(library["id"])
        elif library.get("mediaType") == "book":
            selected.append(library["id"])

    entries = []
    for library_id in selected:
        page = 0
        while True:
            response = requests.get(
                f"{url}/api/libraries/{library_id}/items",
                headers=headers,
                params={"limit": 500, "page": page},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list):
                raise ValueError("Audiobookshelf returned an invalid item list.")
            total = int(data.get("total", 0) or 0)
            entries.extend(
                _audiobookshelf_entry(item)
                for item in results
                if isinstance(item, dict)
            )
            page += 1
            if not results or len(results) < 500 or (total > 0 and page * 500 >= total):
                break
    return entries


def _audiobookshelf_entry(item):
    media = item.get("media") or {}
    metadata = media.get("metadata") or {}
    title = str(metadata.get("title") or "")
    author = str(metadata.get("authorName") or "")
    series = str(metadata.get("seriesName") or "")
    title_tokens, author_tokens, series_tokens = _tokens_for(title, [author], series)
    asin = str(metadata.get("asin") or "").strip().upper()
    return LibraryEntry(
        kind="audiobook",
        title_tokens=title_tokens,
        tokens=title_tokens | author_tokens | series_tokens,
        author_tokens=author_tokens,
        series_tokens=series_tokens,
        isbns=isbn_variants(metadata.get("isbn")),
        asins=frozenset({asin} if asin else ()),
    )


def calibre_fingerprint():
    path = getattr(config, "config_calibre_dir", "")
    if not path:
        return None
    try:
        return os.path.getmtime(os.path.join(path, "metadata.db"))
    except OSError:
        return None


def _tokens_for(title, authors, series):
    title_tokens = clean_title_tokens(title, has_series=bool(series))
    author_tokens = frozenset(
        surname for surname in (author_surname(author) for author in authors or []) if surname
    )
    series_tokens = frozenset(significant_tokens(series))
    return title_tokens, author_tokens, series_tokens


def calibre_entries():
    books = (
        calibre_db.session.query(db.Books)
        .filter(calibre_db.common_filters())
        .options(
            selectinload(db.Books.authors),
            selectinload(db.Books.series),
            selectinload(db.Books.identifiers),
        )
        .all()
    )
    entries = []
    for book in books:
        series = book.series[0].name if book.series else ""
        title_tokens, author_tokens, series_tokens = _tokens_for(
            book.title, [author.name for author in book.authors], series
        )
        isbns = set()
        asins = set()
        external_ids = set()
        for identifier in book.identifiers:
            kind = str(identifier.type or "").strip().lower()
            value = str(identifier.val or "").strip()
            if not value:
                continue
            if kind in _ISBN_TYPES:
                isbns.update(isbn_variants(value))
            elif kind in _ASIN_TYPES:
                asins.add(value.upper())
            elif kind in _EXTERNAL_ID_TYPES:
                external_ids.add((_EXTERNAL_ID_TYPES[kind], value))
        entries.append(
            LibraryEntry(
                kind="calibre",
                title_tokens=title_tokens,
                tokens=title_tokens | author_tokens | series_tokens,
                author_tokens=author_tokens,
                series_tokens=series_tokens,
                isbns=frozenset(isbns),
                asins=frozenset(asins),
                external_ids=frozenset(external_ids),
            )
        )
    return entries


def personal_entries():
    books = ub.session.query(ExternalBook).options(noload(ExternalBook.tags)).all()
    entries = []
    for book in books:
        title_tokens, author_tokens, series_tokens = _tokens_for(
            book.title, book.authors, book.series
        )
        isbns = set(isbn_variants(book.isbn_10))
        isbns.update(isbn_variants(book.isbn_13))
        asins = frozenset({book.asin.upper()} if book.asin else ())
        external_ids = frozenset(
            {(book.metadata_provider, book.metadata_id)}
            if book.metadata_provider and book.metadata_id
            else ()
        )
        entries.append(
            LibraryEntry(
                kind="audiobook" if book.media_type == "audiobook" else "personal",
                title_tokens=title_tokens,
                tokens=title_tokens | author_tokens | series_tokens,
                author_tokens=author_tokens,
                series_tokens=series_tokens,
                isbns=frozenset(isbns),
                asins=asins,
                external_ids=external_ids,
            )
        )
    return entries


def movie_entries():
    movies = ub.session.query(Movie).all()
    entries = []
    for movie in movies:
        entries.append(
            MovieEntry(
                tmdb_id=movie.tmdb_id,
                imdb_id=(movie.imdb_id or "").upper(),
                title_tokens=clean_title_tokens(movie.title),
                original_title_tokens=clean_title_tokens(movie.original_title),
                year=movie.year,
            )
        )
    return entries
