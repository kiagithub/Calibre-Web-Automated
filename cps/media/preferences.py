# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Per-user catalog defaults stored in ``user.view_settings``."""

from sqlalchemy.orm.attributes import flag_modified

from .. import ub
from ..external_books.models import MEDIA_TYPES

VALID_SOURCES = ("all", "calibre", "external")


def catalog_defaults(user):
    settings = getattr(user, "view_settings", None) or {}
    values = settings.get("catalog", {}) if isinstance(settings, dict) else {}
    if not isinstance(values, dict):
        return {}
    defaults = {}
    source = values.get("source")
    if source in VALID_SOURCES:
        defaults["source"] = source
    media_type = values.get("media_type")
    if media_type in MEDIA_TYPES:
        defaults["media_type"] = media_type
    return defaults


def set_catalog_defaults(user, defaults):
    if not isinstance(defaults, dict) or not hasattr(user, "view_settings"):
        return False
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False

    settings = dict(getattr(user, "view_settings", None) or {})
    current = dict(settings.get("catalog", {}) or {})

    if "source" in defaults:
        source = defaults["source"]
        if source in VALID_SOURCES and source != "all":
            current["source"] = source
        else:
            current.pop("source", None)

    if "media_type" in defaults:
        media_type = defaults["media_type"]
        if media_type in MEDIA_TYPES:
            current["media_type"] = media_type
        else:
            current.pop("media_type", None)

    settings["catalog"] = current
    user.view_settings = settings
    try:
        flag_modified(user, "view_settings")
    except Exception:
        pass
    try:
        ub.session.commit()
    except Exception:
        try:
            ub.session.rollback()
        except Exception:
            pass
        return False
    return True
