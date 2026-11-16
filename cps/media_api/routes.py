# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import secrets
from datetime import datetime, timezone

from flask import Blueprint, abort, flash, jsonify, redirect, request, url_for
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from .. import ub
from ..catalog.read_models import MEDIA_TYPE_LABELS
from ..cw_login import current_user
from ..external_books.models import ExternalBook
from ..external_books.query import filtered_external_books
from ..media.stats import collect_media_stats
from ..movie_library.models import Movie
from ..movie_library.query import filtered_movies
from ..render_template import render_title_template
from ..usermanagement import user_login_required
from .auth import api_key_required, hash_key
from .models import ApiKey

media_api = Blueprint("media_api", __name__)

BOOK_SORTS = {
    "title": ExternalBook.title,
    "authors": ExternalBook.authors_json,
    "added": ExternalBook.created_at,
    "published": ExternalBook.published_date,
    "rating": ExternalBook.personal_rating,
}
MOVIE_SORTS = {
    "title": Movie.title,
    "release": Movie.release_date,
    "added": Movie.created_at,
    "rating": Movie.personal_rating,
}


def _pagination():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 24, type=int), 1), 100)
    return page, per_page


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else ""


def _book_json(book):
    return {
        "id": book.id,
        "title": book.title,
        "authors": book.authors,
        "content_type": book.content_type,
        "media_type": book.media_type,
        "media_type_label": MEDIA_TYPE_LABELS.get(book.media_type, book.media_type),
        "series": book.series,
        "series_index": book.series_index,
        "publisher": book.publisher,
        "published_date": book.published_date,
        "languages": book.languages,
        "page_count": book.page_count,
        "narrator": book.narrator,
        "duration_minutes": book.duration_minutes,
        "abridged": book.abridged,
        "audio_format": book.audio_format,
        "isbn_10": book.isbn_10,
        "isbn_13": book.isbn_13,
        "asin": book.asin,
        "location": book.location,
        "rating": book.personal_rating,
        "tags": book.tag_names,
        "cover_url": (
            url_for("external_books.cover", book_id=book.id)
            if book.cover_filename
            else url_for("static", filename="generic_cover.svg")
        ),
        "detail_url": url_for("external_books.detail", book_id=book.id),
        "created_at": _iso(book.created_at),
    }


def _movie_json(movie):
    return {
        "id": movie.id,
        "title": movie.title,
        "original_title": movie.original_title,
        "year": movie.year,
        "release_date": movie.release_date,
        "runtime": movie.runtime,
        "director": movie.director,
        "cast": movie.cast_list,
        "genres": movie.genre_list,
        "content_rating": movie.content_rating,
        "tmdb_id": movie.tmdb_id,
        "imdb_id": movie.imdb_id,
        "media_format": movie.media_format,
        "location": movie.location,
        "rating": movie.personal_rating,
        "watched": movie.is_watched,
        "cover_url": (
            url_for("movies.poster", movie_id=movie.id)
            if movie.poster_filename
            else url_for("static", filename="generic_cover.svg")
        ),
        "detail_url": url_for("movies.detail", movie_id=movie.id),
        "created_at": _iso(movie.created_at),
    }


@media_api.route("/api/media/books")
@api_key_required
def books():
    query_text = request.args.get("q", "").strip()[:200]
    media_type = request.args.get("media_type", "").strip()
    tag = request.args.get("tag", "").strip()[:100]
    sort = request.args.get("sort", "title")
    direction = request.args.get("direction", "asc")
    page, per_page = _pagination()
    query = filtered_external_books(ub.session, query_text, media_type, tag).options(
        selectinload(ExternalBook.tags)
    )
    total = query.count()
    ordering = BOOK_SORTS.get(sort, BOOK_SORTS["title"])
    ordering = ordering.desc() if direction == "desc" else ordering.asc()
    entries = query.order_by(ordering, ExternalBook.id.asc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()
    return jsonify({
        "books": [_book_json(book) for book in entries],
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@media_api.route("/api/media/books/<int:book_id>")
@api_key_required
def book(book_id):
    entry = ub.session.get(ExternalBook, book_id)
    if entry is None:
        abort(404)
    return jsonify(_book_json(entry))


@media_api.route("/api/media/movies")
@api_key_required
def movies():
    query_text = request.args.get("q", "").strip()[:200]
    media_format = request.args.get("format", "").strip()[:40]
    sort = request.args.get("sort", "title")
    direction = request.args.get("direction", "asc")
    page, per_page = _pagination()
    query = filtered_movies(ub.session, query_text, media_format)
    total = query.count()
    ordering = MOVIE_SORTS.get(sort, MOVIE_SORTS["title"])
    ordering = ordering.desc() if direction == "desc" else ordering.asc()
    entries = query.order_by(ordering, Movie.id.asc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()
    return jsonify({
        "movies": [_movie_json(movie) for movie in entries],
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@media_api.route("/api/media/movies/<int:movie_id>")
@api_key_required
def movie(movie_id):
    entry = ub.session.get(Movie, movie_id)
    if entry is None:
        abort(404)
    return jsonify(_movie_json(entry))


@media_api.route("/api/media/stats")
@api_key_required
def stats():
    return jsonify(collect_media_stats())


@media_api.route("/api/media/search")
@api_key_required
def search():
    query_text = request.args.get("q", "").strip()[:200]
    limit = min(max(request.args.get("limit", 10, type=int), 1), 50)
    if not query_text:
        return jsonify({"books": [], "movies": []})
    books = filtered_external_books(ub.session, query_text).options(
        selectinload(ExternalBook.tags)
    ).order_by(ExternalBook.title.asc()).limit(limit).all()
    movies = filtered_movies(ub.session, query_text).order_by(
        Movie.title.asc()
    ).limit(limit).all()
    return jsonify({
        "books": [_book_json(book) for book in books],
        "movies": [_movie_json(movie) for movie in movies],
    })


@media_api.route("/account/api-keys", methods=["GET", "POST"])
@user_login_required
def api_keys():
    raw_key = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:100] or "API key"
        raw_key = secrets.token_urlsafe(32)
        entry = ApiKey(
            user_id=current_user.id,
            name=name,
            key_hash=hash_key(raw_key),
            readonly=True,
        )
        ub.session.add(entry)
        try:
            ub.session.commit()
        except SQLAlchemyError:
            ub.session.rollback()
            flash("The API key could not be created.", "error")
            raw_key = None
        else:
            flash("API key created. Copy it now; it will not be shown again.", "success")
    keys = (
        ub.session.query(ApiKey)
        .filter(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    return render_title_template(
        "media_api/keys.html",
        title="API keys",
        page="api_keys",
        keys=keys,
        raw_key=raw_key,
    )


@media_api.route("/account/api-keys/<int:key_id>/revoke", methods=["POST"])
@user_login_required
def revoke_api_key(key_id):
    entry = ub.session.get(ApiKey, key_id)
    if entry is None:
        abort(404)
    if entry.user_id != current_user.id and not current_user.role_admin():
        abort(403)
    entry.revoked_at = datetime.now(timezone.utc)
    try:
        ub.session.commit()
    except SQLAlchemyError:
        ub.session.rollback()
        flash("The API key could not be revoked.", "error")
    else:
        flash("API key revoked.", "success")
    return redirect(url_for("media_api.api_keys"))


@media_api.route("/media-stats")
@user_login_required
def stats_page():
    return render_title_template(
        "media_api/stats.html",
        title="Collection stats",
        page="stats",
        stats=collect_media_stats(),
    )
