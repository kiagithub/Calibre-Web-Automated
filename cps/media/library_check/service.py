# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cached, fail-open ownership checks for books and movies."""

import threading
import time
from dataclasses import dataclass

from ... import logger
from . import matcher, providers

log = logger.create()

CACHE_TTL_SECONDS = 600
_FAILURE_BACKOFF_SECONDS = 60


@dataclass
class _CacheSlot:
    entries: list | None = None
    fetched_at: float = 0.0
    fingerprint: object = None
    failed_at: float | None = None


_cache = {}
_lock = threading.Lock()


def _user_key():
    try:
        from ...cw_login import current_user

        return getattr(current_user, "id", None)
    except Exception:
        return None


def _cached(name, fingerprint, fetch):
    now = time.monotonic()
    with _lock:
        slot = _cache.get(name)
        fresh = slot is not None and now - slot.fetched_at < CACHE_TTL_SECONDS
        backing_off = slot is not None and slot.failed_at is not None and (
            now - slot.failed_at < _FAILURE_BACKOFF_SECONDS
        )
    if slot is not None and slot.entries is not None and (fresh or backing_off):
        if fresh and slot.fingerprint == fingerprint:
            return slot.entries
        if backing_off:
            return slot.entries
    try:
        entries = fetch()
    except Exception as exc:
        with _lock:
            existing = _cache.get(name)
            if existing is None:
                existing = _CacheSlot()
                _cache[name] = existing
            existing.failed_at = now
        if existing.entries is not None:
            log.warning("library check: %s unavailable (%s); using stale index", name, exc)
            return existing.entries
        log.warning("library check: %s unavailable (%s); failing open", name, exc)
        return []
    with _lock:
        _cache[name] = _CacheSlot(entries, now, fingerprint, None)
    return entries


def book_entries():
    user_id = _user_key()
    entries = _cached(
        f"calibre:{user_id}", providers.calibre_fingerprint(), providers.calibre_entries
    )
    entries = entries + _cached(
        "personal", providers.personal_fingerprint(), providers.personal_entries
    )
    return entries


def movie_entries():
    return _cached("movies", providers.movie_fingerprint(), providers.movie_entries)


def annotate_books(results):
    try:
        entries = book_entries()
    except Exception as exc:
        log.warning("library check: book ownership unavailable: %s", exc)
        return results
    return matcher.annotate_books(results, entries)


def annotate_movies(results):
    try:
        entries = movie_entries()
    except Exception as exc:
        log.warning("library check: movie ownership unavailable: %s", exc)
        return results
    return matcher.annotate_movies(results, entries)


def clear_cache():
    with _lock:
        _cache.clear()
