# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pure matching logic for library ownership checks."""

from dataclasses import dataclass
from typing import Optional

from ..text_match import (
    author_surname,
    clean_title_tokens,
    is_bundle_word,
    is_printing_word,
    isbn_variants,
    strip_series_label,
)

KIND_LABELS = {
    "calibre": "Calibre",
    "personal": "Personal",
    "audiobook": "Audiobook",
    "movie": "Movies",
}


@dataclass(frozen=True)
class LibraryEntry:
    kind: str
    title_tokens: frozenset
    tokens: frozenset
    author_tokens: frozenset
    series_tokens: frozenset = frozenset()
    isbns: frozenset = frozenset()
    asins: frozenset = frozenset()
    external_ids: frozenset = frozenset()


@dataclass(frozen=True)
class MovieEntry:
    tmdb_id: Optional[int]
    imdb_id: str
    title_tokens: frozenset
    original_title_tokens: frozenset
    year: str


@dataclass(frozen=True)
class Match:
    kind: str
    label: str
    collection: bool = False


def _record_isbns(record):
    identifiers = record.get("identifiers") or {}
    values = set()
    for key, value in identifiers.items():
        if str(key).lower() not in {"isbn", "isbn10", "isbn_10", "isbn13", "isbn_13"}:
            continue
        if isinstance(value, (list, tuple, set)):
            values.update(variants for item in value for variants in isbn_variants(item))
        else:
            values.update(isbn_variants(value))
    return frozenset(values)


def _record_asins(record):
    identifiers = record.get("identifiers") or {}
    values = set()
    for key, value in identifiers.items():
        if str(key).lower() in {"amazon", "mobi-asin", "asin"} and value:
            values.add(str(value).strip().upper())
    return frozenset(values)


def _record_external_id(record):
    source = record.get("source") or {}
    provider = str(source.get("id") or "").strip()
    provider_id = str(record.get("id") or "").strip()
    return (provider, provider_id) if provider and provider_id else None


def _author_surnames(values):
    return frozenset(surname for surname in (author_surname(value) for value in values or []) if surname)


def _query_title_tokens(title):
    primary = clean_title_tokens(title)
    stripped = clean_title_tokens(strip_series_label(title, True))
    return primary, stripped


def _extra_match(extra):
    if not extra:
        return "owned"
    if all(is_printing_word(token) for token in extra):
        return "owned"
    if all(is_bundle_word(token) for token in extra):
        return "collection"
    return None


def _match_entry(entry, query_tokens, surnames):
    if entry.author_tokens and surnames and not (surnames & entry.author_tokens):
        return None
    if not query_tokens or not entry.title_tokens:
        return None
    if query_tokens == entry.title_tokens:
        return "owned"
    if query_tokens < entry.title_tokens:
        extra = entry.title_tokens - query_tokens - entry.series_tokens - entry.author_tokens
        return _extra_match(extra)
    if entry.title_tokens < query_tokens:
        extra = query_tokens - entry.title_tokens
        return _extra_match(extra)
    return None


def match_book(record, entries):
    """Return a Match when the metadata record is already owned, or None."""
    external_id = _record_external_id(record)
    isbns = _record_isbns(record)
    asins = _record_asins(record)
    for entry in entries:
        if external_id and external_id in entry.external_ids:
            return Match(entry.kind, KIND_LABELS.get(entry.kind, entry.kind))
        if isbns and entry.isbns and isbns & entry.isbns:
            return Match(entry.kind, KIND_LABELS.get(entry.kind, entry.kind))
        if asins and entry.asins and asins & entry.asins:
            return Match(entry.kind, KIND_LABELS.get(entry.kind, entry.kind))

    primary, stripped = _query_title_tokens(record.get("title"))
    surnames = _author_surnames(record.get("authors"))
    for query_tokens in (primary, stripped):
        if not query_tokens:
            continue
        for entry in entries:
            result = _match_entry(entry, query_tokens, surnames)
            if result == "owned":
                return Match(entry.kind, KIND_LABELS.get(entry.kind, entry.kind))
            if result == "collection":
                return Match(entry.kind, KIND_LABELS.get(entry.kind, entry.kind), collection=True)
    return None


def _year(value):
    text = str(value or "").strip()
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else ""


def match_movie(result, entries):
    """Return a Match when the TMDB record is already in the movie library."""
    try:
        tmdb_id = int(result.get("tmdb_id") or result.get("id") or 0)
    except (TypeError, ValueError):
        tmdb_id = 0
    imdb_id = str(result.get("imdb_id") or "").strip().upper()
    title_tokens = clean_title_tokens(result.get("title"))
    original_tokens = clean_title_tokens(result.get("original_title"))
    year = _year(result.get("year") or result.get("release_date"))

    for entry in entries:
        if tmdb_id and entry.tmdb_id == tmdb_id:
            return Match("movie", KIND_LABELS["movie"])
        if imdb_id and entry.imdb_id and entry.imdb_id == imdb_id:
            return Match("movie", KIND_LABELS["movie"])
        if title_tokens != entry.title_tokens and (
            not original_tokens or original_tokens != entry.original_title_tokens
        ):
            continue
        if year and entry.year and abs(int(year) - int(entry.year)) > 1:
            continue
        return Match("movie", KIND_LABELS["movie"])
    return None


def annotate_books(results, entries):
    for item in results:
        match = match_book(item, entries)
        item["owned"] = bool(match)
        item["owned_as"] = ("Collection" if match.collection else match.label) if match else ""
    return results


def annotate_movies(results, entries):
    for item in results:
        match = match_movie(item, entries)
        item["owned"] = bool(match)
        item["owned_as"] = match.label if match else ""
    return results
