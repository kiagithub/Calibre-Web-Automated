# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from flask import Blueprint, abort, flash, jsonify, redirect, request, url_for
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.attributes import flag_modified

from .. import constants, ub
from ..cw_login import current_user
from ..media.permissions import media_edit_required, media_permissions
from ..pagination import Pagination
from ..render_template import render_title_template
from ..usermanagement import user_login_required
from . import notifications, service
from .models import CONTENT_TYPES, STATUSES, MediaRequest

wishlist = Blueprint("wishlist", __name__, url_prefix="/wishlist")


def _get_request(request_id):
    entry = ub.session.get(MediaRequest, request_id)
    if entry is None:
        abort(404)
    return entry


def _authors(value):
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[&,\n]+", str(value or "")) if item.strip()]


def _identifiers(payload):
    identifiers = payload.get("identifiers")
    if isinstance(identifiers, dict):
        return {key: value for key, value in identifiers.items() if value}
    return {
        key: payload.get(key)
        for key in ("isbn_10", "isbn_13", "asin", "tmdb_id", "release_date")
        if payload.get(key)
    }


@wishlist.route("/")
@user_login_required
def index():
    status = request.args.get("status", "").strip()
    content_type = request.args.get("content_type", "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 24
    query = service.visible_requests(current_user, status, content_type)
    total = query.count()
    entries = query.offset((page - 1) * per_page).limit(per_page).all()
    return render_title_template(
        "wishlist/index.html",
        title="Wishlist",
        page="wishlist",
        entries=entries,
        total=total,
        pagination=Pagination(page, per_page, total),
        status=status,
        content_type=content_type,
        statuses=STATUSES,
        content_types=CONTENT_TYPES,
        **media_permissions(),
    )


@wishlist.route("/new", methods=["GET", "POST"])
@user_login_required
def new():
    errors = []
    if request.method == "POST":
        try:
            entry, created = service.create_request(
                current_user.id,
                request.form.get("content_type", "book"),
                request.form.get("title", ""),
                authors=_authors(request.form.get("authors")),
                director=request.form.get("director", ""),
                identifiers=_identifiers(request.form),
                note=request.form.get("note", ""),
            )
            if created:
                notifications.notify_request("created", entry)
            flash("Request added to the wishlist." if created else "That request is already open.", "success")
            return redirect(url_for("wishlist.index"))
        except service.RequestError as exc:
            errors.append(str(exc))
    return render_title_template(
        "wishlist/new.html",
        title="New request",
        page="wishlist",
        form=request.form,
        errors=errors,
        content_types=CONTENT_TYPES,
        **media_permissions(),
    )


@wishlist.route("/request", methods=["POST"])
@user_login_required
def request_item():
    payload = request.get_json(silent=True) or request.form
    try:
        entry, created = service.create_request(
            current_user.id,
            payload.get("content_type", "book"),
            payload.get("title", ""),
            authors=_authors(payload.get("authors")),
            director=payload.get("director", ""),
            identifiers=_identifiers(payload),
            metadata_provider=payload.get("metadata_provider", ""),
            metadata_id=payload.get("metadata_id", ""),
            metadata_url=payload.get("metadata_url", ""),
            cover_url=payload.get("cover_url", ""),
            note=payload.get("note", ""),
        )
    except service.RequestError as exc:
        return jsonify({"error": str(exc)}), 400
    if created:
        notifications.notify_request("created", entry)
    return jsonify({"ok": True, "id": entry.id, "created": created})


@wishlist.route("/<int:request_id>/approve", methods=["POST"])
@user_login_required
@media_edit_required
def approve(request_id):
    entry = _get_request(request_id)
    try:
        service.approve_request(entry, current_user.id, request.form.get("admin_note", ""))
    except service.RequestError as exc:
        flash(str(exc), "error")
    else:
        notifications.notify_request("approved", entry, request.form.get("admin_note", ""))
        flash("Request approved.", "success")
    return redirect(url_for("wishlist.index"))


@wishlist.route("/<int:request_id>/reject", methods=["POST"])
@user_login_required
@media_edit_required
def reject(request_id):
    entry = _get_request(request_id)
    try:
        service.reject_request(entry, current_user.id, request.form.get("admin_note", ""))
    except service.RequestError as exc:
        flash(str(exc), "error")
    else:
        notifications.notify_request("rejected", entry, request.form.get("admin_note", ""))
        flash("Request rejected.", "success")
    return redirect(url_for("wishlist.index"))


@wishlist.route("/<int:request_id>/cancel", methods=["POST"])
@user_login_required
def cancel(request_id):
    entry = _get_request(request_id)
    try:
        service.cancel_request(entry, current_user.id)
    except service.RequestError as exc:
        flash(str(exc), "error")
    else:
        flash("Request cancelled.", "success")
    return redirect(url_for("wishlist.index"))


@wishlist.route("/<int:request_id>/reopen", methods=["POST"])
@user_login_required
@media_edit_required
def reopen(request_id):
    entry = _get_request(request_id)
    try:
        service.reopen_request(entry, current_user.id)
    except service.RequestError as exc:
        flash(str(exc), "error")
    else:
        flash("Request reopened.", "success")
    return redirect(url_for("wishlist.index"))


@wishlist.route("/notifications", methods=["GET", "POST"])
@user_login_required
def notification_settings():
    user = ub.session.get(ub.User, current_user.id)
    if request.method == "POST":
        settings = dict(user.view_settings or {})
        settings["wishlist_notifications"] = request.form.get("wishlist_notifications") == "on"
        user.view_settings = settings
        flag_modified(user, "view_settings")
        try:
            ub.session.commit()
        except SQLAlchemyError:
            ub.session.rollback()
            flash("Notification preferences could not be saved.", "error")
        else:
            flash("Notification preferences saved.", "success")
        return redirect(url_for("wishlist.notification_settings"))
    enabled = (user.view_settings or {}).get("wishlist_notifications", True)
    return render_title_template(
        "wishlist/notifications.html",
        title="Notifications",
        page="wishlist",
        enabled=enabled,
    )


@wishlist.route("/policies", methods=["GET", "POST"])
@user_login_required
@media_edit_required
def policies():
    users = (
        ub.session.query(ub.User)
        .filter(ub.User.role != constants.ROLE_ANONYMOUS)
        .order_by(ub.User.name)
        .all()
    )
    if request.method == "POST":
        for user in users:
            settings = dict(user.view_settings or {})
            wishlist_settings = dict(settings.get("wishlist", {}) or {})
            raw = request.form.get(f"max_pending_{user.id}")
            if raw is not None:
                try:
                    wishlist_settings["max_pending"] = max(1, min(int(raw), 100))
                except (TypeError, ValueError):
                    pass
            wishlist_settings["requests_allowed"] = (
                request.form.get(f"requests_allowed_{user.id}") == "on"
            )
            settings["wishlist"] = wishlist_settings
            user.view_settings = settings
            flag_modified(user, "view_settings")
        try:
            ub.session.commit()
        except SQLAlchemyError:
            ub.session.rollback()
            flash("Request policies could not be saved.", "error")
        else:
            flash("Request policies saved.", "success")
        return redirect(url_for("wishlist.policies"))
    return render_title_template(
        "wishlist/policies.html",
        title="Request policies",
        page="wishlist",
        users=users,
        max_pending_for=service.max_pending_for,
        requests_allowed=service.requests_allowed,
    )


@wishlist.route("/hardcover-sync", methods=["POST"])
@user_login_required
@media_edit_required
def hardcover_sync():
    from .hardcover_sync import sync_user

    shelf = request.form.get("shelf", "want-to-read")
    content_type = request.form.get("content_type", "book")
    try:
        result = sync_user(current_user, shelf, content_type)
    except Exception as exc:
        flash(f"Hardcover sync failed: {exc}", "error")
    else:
        flash(
            f"Hardcover sync: {result['created']} added, {result['skipped']} skipped.",
            "success",
        )
    return redirect(url_for("wishlist.index"))


@wishlist.route("/<int:request_id>/fulfill", methods=["POST"])
@user_login_required
@media_edit_required
def fulfill(request_id):
    entry = _get_request(request_id)
    if not entry.is_open:
        flash("Only open requests can be fulfilled.", "error")
        return redirect(url_for("wishlist.index"))
    if entry.content_type == "movie":
        return redirect(url_for("movies.new", request_id=entry.id))
    return redirect(url_for("external_books.new", request_id=entry.id))
