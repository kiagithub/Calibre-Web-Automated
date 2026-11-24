# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Collection counters for the media dashboard and read-only API."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from .. import ub
from ..external_books.models import ExternalBook
from ..movie_library.models import Movie
from ..wishlist.models import MediaRequest


def _count(query):
    return int(query.count() or 0)


def collect_media_stats(now=None):
    now = now or datetime.now(timezone.utc)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)

    book_query = ub.session.query(ExternalBook)
    movie_query = ub.session.query(Movie)
    request_query = ub.session.query(MediaRequest)

    by_media_type = {
        media_type: int(count)
        for media_type, count in ub.session.query(
            ExternalBook.media_type, func.count(ExternalBook.id)
        ).group_by(ExternalBook.media_type).all()
    }
    by_format = {
        media_format: int(count)
        for media_format, count in ub.session.query(
            Movie.media_format, func.count(Movie.id)
        ).group_by(Movie.media_format).all()
    }
    requests_by_status = {
        status: int(count)
        for status, count in ub.session.query(
            MediaRequest.status, func.count(MediaRequest.id)
        ).group_by(MediaRequest.status).all()
    }
    requests_by_type = {
        content_type: int(count)
        for content_type, count in ub.session.query(
            MediaRequest.content_type, func.count(MediaRequest.id)
        ).group_by(MediaRequest.content_type).all()
    }

    return {
        "generated_at": now.isoformat(),
        "books": {
            "total": _count(book_query),
            "by_media_type": by_media_type,
            "added_7d": _count(book_query.filter(ExternalBook.created_at >= week)),
            "added_30d": _count(book_query.filter(ExternalBook.created_at >= month)),
        },
        "movies": {
            "total": _count(movie_query),
            "by_format": by_format,
            "added_7d": _count(movie_query.filter(Movie.created_at >= week)),
            "added_30d": _count(movie_query.filter(Movie.created_at >= month)),
        },
        "requests": {
            "total": _count(request_query),
            "by_status": requests_by_status,
            "by_content_type": requests_by_type,
        },
    }
