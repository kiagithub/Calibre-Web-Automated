# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Deduplicate metadata results from multiple providers."""

from .media.text_match import isbn_variants, normalize_text, normalize_title

_ISBN_KEYS = {"isbn", "isbn10", "isbn_10", "isbn13", "isbn_13"}


def _isbn_keys(record):
    values = set()
    for key, value in (record.get("identifiers") or {}).items():
        if str(key).lower() not in _ISBN_KEYS:
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                values.update(isbn_variants(item))
        else:
            values.update(isbn_variants(value))
    return values


def _record_keys(record):
    keys = []
    source = record.get("source") or {}
    provider = str(source.get("id") or "").strip()
    provider_id = str(record.get("id") or "").strip()
    if provider and provider_id:
        keys.append(("id", provider, provider_id))
    for isbn in _isbn_keys(record):
        keys.append(("isbn", isbn))
    title = normalize_title(record.get("title"))
    authors = normalize_text(" ".join(record.get("authors") or []))
    if title:
        keys.append(("title", title, authors))
    return keys


def _has_real_cover(record):
    cover = str(record.get("cover") or "")
    return bool(cover) and "generic_cover" not in cover


def _merge_missing(target, source):
    if not target.get("authors") and source.get("authors"):
        target["authors"] = source["authors"]
    if not target.get("description") or len(str(source.get("description") or "")) > len(
        str(target.get("description") or "")
    ):
        if source.get("description"):
            target["description"] = source["description"]
    for field in ("publisher", "publishedDate", "series", "series_index", "url"):
        if not target.get(field) and source.get(field):
            target[field] = source[field]
    if not _has_real_cover(target) and _has_real_cover(source):
        target["cover"] = source["cover"]
    for field in ("languages", "tags"):
        if source.get(field):
            existing = list(target.get(field) or [])
            seen = {normalize_text(value) for value in existing}
            for value in source[field]:
                folded = normalize_text(value)
                if folded and folded not in seen:
                    existing.append(value)
                    seen.add(folded)
            target[field] = existing
    identifiers = dict(target.get("identifiers") or {})
    for key, value in (source.get("identifiers") or {}).items():
        identifiers.setdefault(key, value)
    target["identifiers"] = identifiers
    return target


def dedupe_records(records):
    """Merge records that share an identifier, ISBN, or normalized title + author."""
    merged = []
    index = {}
    for record in records:
        target = None
        for key in _record_keys(record):
            target = index.get(key)
            if target is not None:
                break
        if target is None:
            target = dict(record)
            merged.append(target)
        else:
            _merge_missing(target, record)
        for key in _record_keys(target):
            index.setdefault(key, target)
    return merged
