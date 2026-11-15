# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from flask import Blueprint, abort, flash, redirect, request, url_for
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import noload

from .. import logger, ub
from ..catalog.read_models import MEDIA_TYPE_LABELS, external_book_card
from ..media import ImageDownloadError, media_delete_required, media_edit_required, media_permissions, serve_artwork
from ..pagination import Pagination
from ..render_template import render_title_template
from ..usermanagement import login_required_if_no_ano, user_login_required
from .covers import artwork_store, cover_limit, remote_cover, uploaded_cover
from .forms import apply_values, validate_form
from .models import CONDITIONS, MEDIA_TYPES, ExternalBook, ExternalBookTag
from .query import filtered_external_books

external_books = Blueprint("external_books", __name__, url_prefix="/books/personal")
log = logger.create()

SORTS = {
    "title": ExternalBook.title,
    "authors": ExternalBook.authors_json,
    "added": ExternalBook.created_at,
    "published": ExternalBook.published_date,
    "rating": ExternalBook.personal_rating,
}



def _get_book(book_id):
    book = ub.session.get(ExternalBook, book_id)
    if book is None:
        abort(404)
    return book


def _form_context(book=None, errors=None):
    return {
        "book": book,
        "form": request.form if request.method == "POST" else {},
        "errors": errors or [],
        "media_types": [(value, MEDIA_TYPE_LABELS[value]) for value in MEDIA_TYPES],
        "conditions": CONDITIONS,
        "metadata_search_url": url_for("metadata.metadata_search"),
        **media_permissions(),
    }


def _selected_cover(values, errors, max_bytes):
    upload = uploaded_cover(request.files.get("cover"), errors, max_bytes)
    if upload or errors or not values["cover_url"]:
        return upload
    try:
        return remote_cover(values["cover_url"], max_bytes)
    except ImageDownloadError as exc:
        log.warning("Could not download external-book cover: %s", exc)
        flash("The book was saved without updating its remote cover.", "warning")
        return None


def _delete_old_cover(old_filename):
    if old_filename:
        try:
            artwork_store().delete(old_filename)
        except OSError as exc:
            log.warning("Could not remove replaced external-book cover %s: %s", old_filename, exc)


def _save_book(book, values, errors, is_new):
    max_bytes = cover_limit() if request.files.get("cover") or values["cover_url"] else None
    cover = _selected_cover(values, errors, max_bytes)
    if errors:
        return False, 400
    old_filename = book.cover_filename or ""
    new_filename = None
    try:
        apply_values(book, values)
        if is_new:
            ub.session.add(book)
        ub.session.flush()
        if cover:
            new_filename = artwork_store().stage(
                cover[0], cover[1], f"book-{book.id}", max_bytes=max_bytes
            )
            book.cover_filename = new_filename
        elif values["remove_cover"]:
            book.cover_filename = ""
        ub.session.commit()
    except (SQLAlchemyError, OSError, ValueError) as exc:
        ub.session.rollback()
        if new_filename:
            try:
                artwork_store().discard(new_filename)
            except OSError:
                log.warning("Could not discard uncommitted external-book cover %s", new_filename)
        log.error("Could not save external-book change: %s", exc)
        errors.append("The book could not be saved. Please try again.")
        return False, 500
    if cover or values["remove_cover"]:
        _delete_old_cover(old_filename)
    return True, 200


@external_books.route("/")
@login_required_if_no_ano
def index():
    query_text = request.args.get("q", "").strip()[:200]
    media_type = request.args.get("media_type", "").strip()
    if media_type not in MEDIA_TYPES:
        media_type = ""
    tag = request.args.get("tag", "").strip()[:100]
    sort = request.args.get("sort", "title")
    direction = request.args.get("direction", "asc")
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 24

    query = filtered_external_books(ub.session, query_text, media_type, tag).options(noload(ExternalBook.tags))
    total = query.count()
    ordering = SORTS.get(sort, SORTS["title"])
    ordering = ordering.desc() if direction == "desc" else ordering.asc()
    entries = query.order_by(ordering, ExternalBook.id.asc()).offset((page - 1) * per_page).limit(per_page).all()
    last_page = max((total - 1) // per_page + 1, 1)
    if page > 1 and not entries and total:
        return redirect(url_for(
            "external_books.index", q=query_text, media_type=media_type, tag=tag,
            sort=sort, direction=direction, page=last_page,
        ))
    tags = [row[0] for row in ub.session.query(ExternalBookTag.name).distinct().order_by(ExternalBookTag.name).all()]
    return render_title_template(
        "external_books/index.html", title="Personal Books", page="books", entries=[
            external_book_card(book) for book in entries
        ], pagination=Pagination(page, per_page, total), total=total,
        query_text=query_text, selected_type=media_type, selected_tag=tag,
        sort=sort, direction=direction, tags=tags,
        types=[(value, MEDIA_TYPE_LABELS[value]) for value in MEDIA_TYPES],
        **media_permissions(),
    )


@external_books.route("/<int:book_id>")
@login_required_if_no_ano
def detail(book_id):
    book = _get_book(book_id)
    return render_title_template(
        "external_books/detail.html", title=book.title, page="books", book=book, **media_permissions()
    )


@external_books.route("/new", methods=["GET", "POST"])
@user_login_required
@media_edit_required
def new():
    if request.method == "POST":
        values, errors = validate_form(request.form)
        book = ExternalBook()
        saved, status = _save_book(book, values, errors, True)
        if saved:
            flash(f"Added {book.title} to your personal book library.", "success")
            return redirect(url_for("external_books.detail", book_id=book.id))
        return render_title_template(
            "external_books/form.html", title="Add Book", page="books",
            **_form_context(errors=errors)
        ), status
    return render_title_template(
        "external_books/form.html", title="Add Book", page="books", **_form_context()
    )


@external_books.route("/<int:book_id>/edit", methods=["GET", "POST"])
@user_login_required
@media_edit_required
def edit(book_id):
    book = _get_book(book_id)
    if request.method == "POST":
        values, errors = validate_form(request.form)
        saved, status = _save_book(book, values, errors, False)
        if saved:
            flash("Book details updated.", "success")
            return redirect(url_for("external_books.detail", book_id=book.id))
        return render_title_template(
            "external_books/form.html", title=f"Edit {book.title}", page="books",
            **_form_context(book, errors)
        ), status
    return render_title_template(
        "external_books/form.html", title=f"Edit {book.title}", page="books", **_form_context(book)
    )


@external_books.route("/<int:book_id>/delete", methods=["POST"])
@user_login_required
@media_delete_required
def delete(book_id):
    book = _get_book(book_id)
    title = book.title
    cover_filename = book.cover_filename
    ub.session.delete(book)
    try:
        ub.session.commit()
    except SQLAlchemyError as exc:
        ub.session.rollback()
        log.error("Could not delete external book %s: %s", book_id, exc)
        flash("The book could not be deleted. Please try again.", "error")
        return redirect(url_for("external_books.detail", book_id=book_id))
    if cover_filename:
        try:
            artwork_store().delete(cover_filename)
        except OSError as exc:
            log.warning("Could not remove cover for deleted external book %s: %s", book_id, exc)
    flash(f"Deleted {title} from your personal book library.", "success")
    return redirect(url_for("external_books.index"))


@external_books.route("/<int:book_id>/cover")
@login_required_if_no_ano
def cover(book_id):
    book = _get_book(book_id)
    return serve_artwork(artwork_store(), book.cover_filename)
