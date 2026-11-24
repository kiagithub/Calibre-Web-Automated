# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import or_

from ..media.queries import escaped_like
from .models import ExternalBook, ExternalBookTag, normalize_tag_name


def filtered_external_books(session, query_text="", media_type="", tag=""):
    """Shared filtering for the dedicated and combined personal-book views."""
    query = session.query(ExternalBook)
    if query_text:
        term = escaped_like(query_text)
        query = query.filter(or_(
            ExternalBook.title.ilike(term, escape="\\"),
            ExternalBook.authors_json.ilike(term, escape="\\"),
            ExternalBook.publisher.ilike(term, escape="\\"),
            ExternalBook.series.ilike(term, escape="\\"),
            ExternalBook.isbn_10.ilike(term, escape="\\"),
            ExternalBook.isbn_13.ilike(term, escape="\\"),
            ExternalBook.asin.ilike(term, escape="\\"),
        ))
    if media_type:
        query = query.filter(ExternalBook.media_type == media_type)
    if tag:
        query = query.filter(ExternalBook.tags.any(
            ExternalBookTag.normalized_name == normalize_tag_name(tag)
        ))
    return query
