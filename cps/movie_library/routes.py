# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import uuid
from datetime import date, datetime, timezone
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    request,
    send_file,
    url_for,
)
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from .. import constants, logger, ub
from ..cw_login import current_user
from ..pagination import Pagination
from ..render_template import render_title_template
from ..usermanagement import login_required_if_no_ano, user_login_required
from .metadata import MAX_POSTER_BYTES, MovieMetadataError, TMDBClient, image_type
from .models import Movie

movies = Blueprint("movies", __name__, url_prefix="/movies")
log = logger.create()

MEDIA_FORMATS = ("DVD", "Blu-ray", "4K UHD", "VHS", "LaserDisc", "Digital", "Other")
CONDITIONS = ("New", "Like new", "Good", "Fair", "Poor")
SORTS = {
    "title": Movie.title,
    "release": Movie.release_date,
    "added": Movie.created_at,
    "rating": Movie.personal_rating,
}
TEXT_FIELDS = {
    "title": 300,
    "original_title": 300,
    "overview": 20000,
    "director": 500,
    "cast_members": 5000,
    "genres": 500,
    "content_rating": 20,
    "imdb_id": 20,
    "media_format": 40,
    "location": 200,
    "barcode": 64,
    "edition": 200,
    "condition": 40,
    "notes": 10000,
}
METADATA_FIELDS = (
    "title", "original_title", "overview", "release_date", "runtime", "director",
    "cast_members", "genres", "content_rating", "tmdb_rating", "tmdb_id", "imdb_id",
)


def edit_required(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        if not (current_user.role_edit() or current_user.role_admin()):
            abort(403)
        return func(*args, **kwargs)
    return decorated


def delete_required(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        if not (current_user.role_delete_books() or current_user.role_admin()):
            abort(403)
        return func(*args, **kwargs)
    return decorated


def _get_movie(movie_id):
    movie = ub.session.get(Movie, movie_id)
    if movie is None:
        abort(404)
    return movie


def _client():
    return TMDBClient()


def _commit():
    try:
        ub.session.commit()
        return True
    except SQLAlchemyError as exc:
        ub.session.rollback()
        log.error("Could not save movie library change: %s", exc)
        flash("The movie could not be saved. Please try again.", "error")
        return False


def _parse_date(value, label, errors):
    if not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        errors.append(f"{label} must be a valid date.")
        return value


def _parse_int(value, label, minimum, maximum, errors, optional=True):
    if not value and optional:
        return None
    try:
        number = int(value)
        if not minimum <= number <= maximum:
            raise ValueError
        return number
    except (TypeError, ValueError):
        errors.append(f"{label} must be between {minimum} and {maximum}.")
        return None


def _validated_form():
    values = {}
    errors = []
    for field, limit in TEXT_FIELDS.items():
        value = request.form.get(field, "").strip()
        if len(value) > limit:
            errors.append(f"{field.replace('_', ' ').title()} must be {limit} characters or fewer.")
        values[field] = value
    if not values["title"]:
        errors.append("Title is required.")
    if not values["media_format"]:
        errors.append("Physical format is required.")
    for field, label in (("release_date", "Release date"), ("date_acquired", "Date acquired")):
        values[field] = _parse_date(request.form.get(field, "").strip(), label, errors)
    values["runtime"] = _parse_int(request.form.get("runtime"), "Runtime", 1, 2000, errors)
    values["personal_rating"] = _parse_int(request.form.get("personal_rating"), "Personal rating", 0, 10, errors)
    values["tmdb_id"] = _parse_int(request.form.get("tmdb_id"), "TMDB ID", 1, 2147483647, errors)
    values["is_watched"] = request.form.get("is_watched") == "on"
    return values, errors


def _apply_values(movie, values):
    for field in TEXT_FIELDS:
        setattr(movie, field, values[field])
    for field in ("release_date", "date_acquired", "runtime", "personal_rating", "tmdb_id", "is_watched"):
        setattr(movie, field, values[field])
    movie.updated_at = datetime.now(timezone.utc)


def _apply_metadata(movie, metadata):
    for field in METADATA_FIELDS:
        if field in metadata:
            setattr(movie, field, metadata[field])
    movie.metadata_updated_at = datetime.now(timezone.utc)
    movie.updated_at = datetime.now(timezone.utc)


def _cover_directory():
    if not ub.app_DB_path:
        raise RuntimeError("The application database path is not initialized.")
    return os.path.join(os.path.dirname(ub.app_DB_path), "movie_covers")


def _save_poster(movie, data, extension):
    extension = image_type(data)
    if not extension or len(data) > MAX_POSTER_BYTES:
        raise ValueError("Unsupported or oversized poster image")
    directory = _cover_directory()
    os.makedirs(directory, mode=0o750, exist_ok=True)
    old_filename = movie.poster_filename
    filename = f"movie-{movie.id}-{uuid.uuid4().hex}.{extension}"
    temporary = os.path.join(directory, f".{filename}.tmp")
    destination = os.path.join(directory, filename)
    try:
        with open(temporary, "wb") as poster_file:
            poster_file.write(data)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    movie.poster_filename = filename
    if old_filename and old_filename != filename:
        _delete_poster_file(old_filename)


def _delete_poster_file(filename):
    if not filename or os.path.basename(filename) != filename:
        return
    path = os.path.join(_cover_directory(), filename)
    if os.path.isfile(path):
        os.unlink(path)


def _uploaded_poster(errors):
    upload = request.files.get("poster")
    if not upload or not upload.filename:
        return None
    data = upload.read(MAX_POSTER_BYTES + 1)
    extension = image_type(data)
    if len(data) > MAX_POSTER_BYTES:
        errors.append("Poster images must be 8 MB or smaller.")
    elif not extension:
        errors.append("Poster images must be JPEG, PNG, or WebP files.")
    else:
        return data, extension
    return None


def _form_context(movie=None, errors=None):
    return {
        "movie": movie,
        "form": request.form if request.method == "POST" else {},
        "errors": errors or [],
        "formats": MEDIA_FORMATS,
        "conditions": CONDITIONS,
        "metadata_configured": _client().configured,
    }


def _refresh_poster(movie, poster_url):
    if not poster_url:
        return ""
    try:
        data, extension = _client().download_poster(poster_url)
        _save_poster(movie, data, extension)
        return ""
    except (MovieMetadataError, OSError, ValueError) as exc:
        log.warning("Could not cache poster for movie %s: %s", movie.id, exc)
        return "Metadata was saved, but the poster could not be updated."


@movies.route("/")
@login_required_if_no_ano
def index():
    query_text = request.args.get("q", "").strip()[:200]
    media_format = request.args.get("format", "").strip()[:40]
    sort = request.args.get("sort", "title")
    direction = request.args.get("direction", "asc")
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 24

    query = ub.session.query(Movie)
    if query_text:
        escaped = query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = f"%{escaped}%"
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
    total = query.count()
    sort_column = SORTS.get(sort, SORTS["title"])
    ordering = sort_column.desc() if direction == "desc" else sort_column.asc()
    entries = query.order_by(ordering, Movie.id.asc()).offset((page - 1) * per_page).limit(per_page).all()
    if page > 1 and not entries and total:
        return redirect(url_for("movies.index", q=query_text, format=media_format,
                                sort=sort, direction=direction, page=max((total - 1) // per_page + 1, 1)))
    formats = [row[0] for row in ub.session.query(Movie.media_format).distinct().order_by(Movie.media_format).all()]
    return render_title_template(
        "movies/index.html", title="Movies", page="movies", entries=entries,
        pagination=Pagination(page, per_page, total), total=total, formats=formats,
        query_text=query_text, selected_format=media_format, sort=sort, direction=direction,
        metadata_configured=_client().configured,
    )


@movies.route("/<int:movie_id>")
@login_required_if_no_ano
def detail(movie_id):
    movie = _get_movie(movie_id)
    return render_title_template("movies/detail.html", title=movie.title,
                                 page="movies", movie=movie)


@movies.route("/new", methods=["GET", "POST"])
@user_login_required
@edit_required
def new():
    if request.method == "POST":
        values, errors = _validated_form()
        poster = _uploaded_poster(errors)
        if errors:
            return render_title_template("movies/form.html", title="Add Movie", page="movies",
                                         **_form_context(errors=errors)), 400
        movie = Movie()
        _apply_values(movie, values)
        ub.session.add(movie)
        if not _commit():
            return render_title_template("movies/form.html", title="Add Movie", page="movies",
                                         **_form_context()), 500
        if poster and movie.id:
            try:
                _save_poster(movie, *poster)
                _commit()
            except (OSError, ValueError):
                flash("The movie was saved, but its poster could not be stored.", "warning")
        flash(f"Added {movie.title} to your movie library.", "success")
        return redirect(url_for("movies.detail", movie_id=movie.id))
    return render_title_template("movies/form.html", title="Add Movie", page="movies", **_form_context())


@movies.route("/<int:movie_id>/edit", methods=["GET", "POST"])
@user_login_required
@edit_required
def edit(movie_id):
    movie = _get_movie(movie_id)
    if request.method == "POST":
        values, errors = _validated_form()
        poster = _uploaded_poster(errors)
        if errors:
            return render_title_template("movies/form.html", title=f"Edit {movie.title}", page="movies",
                                         **_form_context(movie, errors)), 400
        _apply_values(movie, values)
        if poster:
            try:
                _save_poster(movie, *poster)
            except (OSError, ValueError):
                errors.append("The poster could not be stored.")
        if errors:
            ub.session.rollback()
            return render_title_template("movies/form.html", title=f"Edit {movie.title}", page="movies",
                                         **_form_context(movie, errors)), 400
        if _commit():
            flash("Movie details updated.", "success")
            return redirect(url_for("movies.detail", movie_id=movie.id))
    return render_title_template("movies/form.html", title=f"Edit {movie.title}", page="movies",
                                 **_form_context(movie))


@movies.route("/<int:movie_id>/delete", methods=["POST"])
@user_login_required
@delete_required
def delete(movie_id):
    movie = _get_movie(movie_id)
    title = movie.title
    poster_filename = movie.poster_filename
    ub.session.delete(movie)
    if _commit():
        try:
            _delete_poster_file(poster_filename)
        except OSError as exc:
            log.warning("Could not remove poster for deleted movie %s: %s", movie_id, exc)
        flash(f"Deleted {title} from your movie library.", "success")
    return redirect(url_for("movies.index"))


@movies.route("/<int:movie_id>/poster")
@login_required_if_no_ano
def poster(movie_id):
    movie = _get_movie(movie_id)
    if movie.poster_filename and os.path.basename(movie.poster_filename) == movie.poster_filename:
        path = os.path.join(_cover_directory(), movie.poster_filename)
        if os.path.isfile(path):
            response = send_file(path, conditional=True, max_age=3600)
            response.headers["Cache-Control"] = "private, max-age=3600"
            return response
    return send_file(os.path.join(constants.BASE_DIR, "cps", "static", "generic_cover.svg"))


@movies.route("/metadata/search", methods=["POST"])
@user_login_required
@edit_required
def metadata_search():
    payload = request.get_json(silent=True) or request.form
    query = payload.get("query", "")
    year = payload.get("year", "")
    try:
        results = _client().search(query, year)
        return jsonify({"results": results})
    except MovieMetadataError as exc:
        return jsonify({"error": str(exc)}), 503 if not _client().configured else 400


@movies.route("/import", methods=["POST"])
@user_login_required
@edit_required
def import_movie():
    try:
        metadata = _client().details(request.form.get("tmdb_id"))
    except MovieMetadataError as exc:
        flash(str(exc), "error")
        return redirect(url_for("movies.new"))
    movie = Movie(media_format=request.form.get("media_format", "Blu-ray").strip()[:40] or "Blu-ray",
                  location=request.form.get("location", "").strip()[:200])
    _apply_metadata(movie, metadata)
    ub.session.add(movie)
    if not _commit():
        return redirect(url_for("movies.new"))
    warning = _refresh_poster(movie, metadata.get("poster_url"))
    if warning:
        flash(warning, "warning")
    _commit()
    flash(f"Added {movie.title} with metadata from TMDB.", "success")
    return redirect(url_for("movies.edit", movie_id=movie.id))


@movies.route("/<int:movie_id>/metadata/apply", methods=["POST"])
@user_login_required
@edit_required
def metadata_apply(movie_id):
    movie = _get_movie(movie_id)
    try:
        metadata = _client().details(request.form.get("tmdb_id"))
    except MovieMetadataError as exc:
        flash(str(exc), "error")
        return redirect(url_for("movies.edit", movie_id=movie.id))
    _apply_metadata(movie, metadata)
    if not _commit():
        return redirect(url_for("movies.edit", movie_id=movie.id))
    warning = _refresh_poster(movie, metadata.get("poster_url"))
    if not warning and metadata.get("poster_url") and not _commit():
        return redirect(url_for("movies.edit", movie_id=movie.id))
    if warning:
        flash(warning, "warning")
    else:
        flash("Movie metadata updated from TMDB. Physical-copy details were preserved.", "success")
    return redirect(url_for("movies.detail", movie_id=movie.id))
