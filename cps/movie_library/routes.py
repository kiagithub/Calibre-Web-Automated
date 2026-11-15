# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import date, datetime, timezone

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    request,
    url_for,
)
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from .. import logger, ub
from ..catalog.read_models import movie_card
from ..media.artwork import ArtworkStore, serve_artwork
from ..media.images import ImageTooLargeError, InvalidImageError, read_image_upload
from ..media.permissions import media_delete_required, media_edit_required, media_permissions
from ..media.queries import escaped_like
from ..pagination import Pagination
from ..render_template import render_title_template
from ..usermanagement import login_required_if_no_ano, user_login_required
from .metadata import MAX_POSTER_BYTES, MovieMetadataError, TMDBClient
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

# Backwards-compatible names for callers that imported the movie decorators.
edit_required = media_edit_required
delete_required = media_delete_required


def _get_movie(movie_id):
    movie = ub.session.get(Movie, movie_id)
    if movie is None:
        abort(404)
    return movie


def _client():
    return TMDBClient()


def _database_error(exc):
    ub.session.rollback()
    log.error("Could not save movie library change: %s", exc)
    flash("The movie could not be saved. Please try again.", "error")


def _flush():
    try:
        ub.session.flush()
        return True
    except SQLAlchemyError as exc:
        _database_error(exc)
        return False


def _commit():
    try:
        ub.session.commit()
        return True
    except SQLAlchemyError as exc:
        _database_error(exc)
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
    elif values["media_format"] not in MEDIA_FORMATS:
        errors.append("Select a valid physical format.")
    values["condition"] = values["condition"] or "Good"
    if values["condition"] not in CONDITIONS:
        errors.append("Select a valid condition.")
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


def _cover_store():
    return ArtworkStore(ub.app_DB_path, "movie_covers")


def _cover_directory():
    return _cover_store().root


def _save_poster(movie, data, extension):
    """Stage a poster and update the model; the caller owns the transaction."""
    old_filename = movie.poster_filename
    filename = _cover_store().stage(
        data, extension, f"movie-{movie.id}", max_bytes=MAX_POSTER_BYTES,
    )
    movie.poster_filename = filename
    return old_filename, filename


def _discard_staged_poster(filename):
    if not filename:
        return
    try:
        _cover_store().discard(filename)
    except (OSError, ValueError) as exc:
        log.warning("Could not remove uncommitted movie poster %s: %s", filename, exc)


def _delete_poster_file(filename):
    _cover_store().delete(filename)


def _delete_poster_after_commit(filename, movie_id):
    if not filename:
        return
    try:
        _delete_poster_file(filename)
    except (OSError, ValueError) as exc:
        log.warning("Could not remove old poster for movie %s: %s", movie_id, exc)


def _uploaded_poster(errors):
    try:
        poster = read_image_upload(request.files.get("poster"), max_bytes=MAX_POSTER_BYTES)
    except ImageTooLargeError:
        errors.append("Poster images must be 8 MB or smaller.")
        return None
    except InvalidImageError:
        errors.append("Poster images must be JPEG, PNG, or WebP files.")
        return None
    return (poster.data, poster.extension) if poster else None


def _form_context(movie=None, errors=None):
    return {
        "movie": movie,
        "form": request.form if request.method == "POST" else {},
        "errors": errors or [],
        "formats": MEDIA_FORMATS,
        "conditions": CONDITIONS,
        "metadata_configured": _client().configured,
        **media_permissions(),
    }


def _download_poster(poster_url):
    """Download before opening a database write transaction."""
    if not poster_url:
        return None, ""
    try:
        return _client().download_poster(poster_url), ""
    except MovieMetadataError as exc:
        log.warning("Could not download TMDB poster: %s", exc)
        return None, "Metadata was saved, but the poster could not be updated."


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
    total = query.count()
    sort_column = SORTS.get(sort, SORTS["title"])
    ordering = sort_column.desc() if direction == "desc" else sort_column.asc()
    entries = query.order_by(ordering, Movie.id.asc()).offset((page - 1) * per_page).limit(per_page).all()
    if page > 1 and not entries and total:
        return redirect(url_for("movies.index", q=query_text, format=media_format,
                                sort=sort, direction=direction, page=max((total - 1) // per_page + 1, 1)))
    formats = [row[0] for row in ub.session.query(Movie.media_format).distinct().order_by(Movie.media_format).all()]
    return render_title_template(
        "movies/index.html", title="Movies", page="movies",
        entries=[movie_card(movie) for movie in entries],
        pagination=Pagination(page, per_page, total), total=total, formats=formats,
        query_text=query_text, selected_format=media_format, sort=sort, direction=direction,
        **media_permissions(),
    )


@movies.route("/<int:movie_id>")
@login_required_if_no_ano
def detail(movie_id):
    movie = _get_movie(movie_id)
    return render_title_template("movies/detail.html", title=movie.title,
                                 page="movies", movie=movie, **media_permissions())


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
        if not _flush():
            return render_title_template("movies/form.html", title="Add Movie", page="movies",
                                         **_form_context()), 500
        staged_poster = ""
        poster_warning = False
        if poster:
            try:
                _, staged_poster = _save_poster(movie, *poster)
            except (OSError, ValueError) as exc:
                log.warning("Could not store poster for new movie %s: %s", movie.id, exc)
                poster_warning = True
        if not _commit():
            _discard_staged_poster(staged_poster)
            return render_title_template("movies/form.html", title="Add Movie", page="movies",
                                         **_form_context()), 500
        if poster_warning:
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
        old_poster = ""
        staged_poster = ""
        if poster:
            try:
                old_poster, staged_poster = _save_poster(movie, *poster)
            except (OSError, ValueError) as exc:
                log.warning("Could not store poster for movie %s: %s", movie.id, exc)
                errors.append("The poster could not be stored.")
        if errors:
            ub.session.rollback()
            _discard_staged_poster(staged_poster)
            return render_title_template("movies/form.html", title=f"Edit {movie.title}", page="movies",
                                         **_form_context(movie, errors)), 400
        if _commit():
            if staged_poster and old_poster != staged_poster:
                _delete_poster_after_commit(old_poster, movie.id)
            flash("Movie details updated.", "success")
            return redirect(url_for("movies.detail", movie_id=movie.id))
        _discard_staged_poster(staged_poster)
        return render_title_template("movies/form.html", title=f"Edit {movie.title}", page="movies",
                                     **_form_context(movie)), 500
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
        _delete_poster_after_commit(poster_filename, movie_id)
        flash(f"Deleted {title} from your movie library.", "success")
    return redirect(url_for("movies.index"))


@movies.route("/<int:movie_id>/poster")
@login_required_if_no_ano
def poster(movie_id):
    movie = _get_movie(movie_id)
    return serve_artwork(_cover_store(), movie.poster_filename)


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
    media_format = request.form.get("media_format", "Blu-ray").strip()[:40] or "Blu-ray"
    condition = request.form.get("condition", "Good").strip()[:40] or "Good"
    if media_format not in MEDIA_FORMATS:
        flash("Select a valid physical format.", "error")
        return redirect(url_for("movies.new"))
    if condition not in CONDITIONS:
        flash("Select a valid condition.", "error")
        return redirect(url_for("movies.new"))
    try:
        metadata = _client().details(request.form.get("tmdb_id"))
    except MovieMetadataError as exc:
        flash(str(exc), "error")
        return redirect(url_for("movies.new"))
    poster, warning = _download_poster(metadata.get("poster_url"))
    movie = Movie(media_format=media_format, condition=condition,
                  location=request.form.get("location", "").strip()[:200])
    _apply_metadata(movie, metadata)
    ub.session.add(movie)
    if not _flush():
        return redirect(url_for("movies.new"))
    staged_poster = ""
    if poster:
        try:
            _old_poster, staged_poster = _save_poster(movie, *poster)
        except (OSError, ValueError) as exc:
            log.warning("Could not store poster for imported movie %s: %s", movie.id, exc)
            warning = "Metadata was saved, but the poster could not be updated."
    if not _commit():
        _discard_staged_poster(staged_poster)
        return redirect(url_for("movies.new"))
    if warning:
        flash(warning, "warning")
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
    poster, warning = _download_poster(metadata.get("poster_url"))
    _apply_metadata(movie, metadata)
    old_poster = ""
    staged_poster = ""
    if poster:
        try:
            old_poster, staged_poster = _save_poster(movie, *poster)
        except (OSError, ValueError) as exc:
            log.warning("Could not store updated poster for movie %s: %s", movie.id, exc)
            warning = "Metadata was saved, but the poster could not be updated."
    if not _commit():
        _discard_staged_poster(staged_poster)
        return redirect(url_for("movies.edit", movie_id=movie.id))
    if staged_poster and old_poster != staged_poster:
        _delete_poster_after_commit(old_poster, movie.id)
    if warning:
        flash(warning, "warning")
    else:
        flash("Movie metadata updated from TMDB. Physical-copy details were preserved.", "success")
    return redirect(url_for("movies.detail", movie_id=movie.id))
