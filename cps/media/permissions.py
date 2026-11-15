# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Permission decorators shared by non-Calibre media catalogs."""

from functools import wraps

from flask import abort

from ..cw_login import current_user


def media_permissions(user=None):
    """Return the presentation and route permissions for a media collection."""
    user = current_user if user is None else user
    authenticated = bool(user and user.is_authenticated)
    return {
        "can_edit_media": authenticated and bool(user.role_edit() or user.role_admin()),
        "can_delete_media": authenticated and bool(user.role_delete_books() or user.role_admin()),
    }


def media_edit_required(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        if not media_permissions()["can_edit_media"]:
            abort(403)
        return func(*args, **kwargs)
    return decorated


def media_delete_required(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        if not media_permissions()["can_delete_media"]:
            abort(403)
        return func(*args, **kwargs)
    return decorated
