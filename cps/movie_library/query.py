# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import or_

from ..media.queries import escaped_like
from .models import Movie


def filtered_movies(session, query_text="", media_format=""):
    query = session.query(Movie)
    if query_text:
        term = escaped_like(query_text)
        query = query.filter(or_(
            Movie.title.ilike(term, escape="\\"),
            Movie.original_title.ilike(term, escape="\\"),
            Movie.director.ilike(term, escape="\\"),
            Movie.cast_members.ilike(term, escape="\\"),
            Movie.genres.ilike(term, escape="\\"),
            Movie.location.ilike(term, escape="\\"),
            Movie.barcode.ilike(term, escape="\\"),
        ))
    if media_format:
        query = query.filter(Movie.media_format == media_format)
    return query
