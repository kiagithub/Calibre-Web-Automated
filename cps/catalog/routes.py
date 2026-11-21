# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from flask import Blueprint, redirect, request, url_for

from ..cw_login import current_user
from ..external_books.models import MEDIA_TYPES
from ..media import media_permissions
from ..media.preferences import catalog_defaults, set_catalog_defaults
from ..pagination import KeysetPagination
from ..render_template import render_title_template
from ..usermanagement import login_required_if_no_ano
from .read_models import MEDIA_TYPE_LABELS
from .service import available_tags, combined_books

catalog = Blueprint("catalog", __name__, url_prefix="/books")


def _page_url(filters, cursor, direction):
    params = {
        key: value for key, value in filters.items()
        if value and not (key == "source" and value == "all")
    }
    params.update({"cursor": cursor, "dir": direction})
    return url_for("catalog.index", **params)


@catalog.route("/")
@login_required_if_no_ano
def index():
    defaults = catalog_defaults(current_user)
    default_source = defaults.get("source", "all")
    default_media_type = defaults.get("media_type", "")

    query_text = request.args.get("q", "").strip()[:200]
    source = request.args.get("source", default_source)
    if source not in ("all", "calibre", "external"):
        source = "all"
    media_type = request.args.get("media_type", default_media_type).strip()
    if media_type not in MEDIA_TYPES:
        media_type = ""
    tag = request.args.get("tag", "").strip()[:100]
    cursor = request.args.get("cursor", "").strip()
    direction = request.args.get("dir", "next")
    if direction not in ("next", "prev"):
        direction = "next"

    if request.args.get("save_defaults") == "1" and getattr(current_user, "is_authenticated", False):
        set_catalog_defaults(current_user, {"source": source, "media_type": media_type})
        defaults = catalog_defaults(current_user)

    filters = {"q": query_text, "source": source, "media_type": media_type, "tag": tag}
    if "page" in request.args and not cursor:
        # Numbered page links are gone; keep old bookmarks working at the start.
        return redirect(url_for("catalog.index", **filters))

    result = combined_books(
        cursor=cursor or None, direction=direction, per_page=24,
        query_text=query_text, source=source, media_type=media_type, tag=tag,
    )
    prev_url = _page_url(filters, result.prev_cursor, "prev") if result.has_prev else None
    next_url = _page_url(filters, result.next_cursor, "next") if result.has_next else None
    pagination = KeysetPagination(prev_url=prev_url, next_url=next_url)
    tags = available_tags()
    return render_title_template(
        "catalog/index.html", title=f"Books ({result.total})", page="books",
        entries=result.cards, total=result.total,
        pagination=pagination,
        query_text=query_text, searchterm=query_text, selected_source=source, selected_type=media_type,
        selected_tag=tag, tags=tags,
        types=[(value, MEDIA_TYPE_LABELS[value]) for value in MEDIA_TYPES],
        catalog_defaults=defaults,
        **media_permissions(),
    )


@catalog.route("/defaults", methods=["POST"])
@login_required_if_no_ano
def save_defaults():
    if getattr(current_user, "is_authenticated", False):
        source = request.form.get("source", "all")
        media_type = request.form.get("media_type", "")
        set_catalog_defaults(current_user, {"source": source, "media_type": media_type})
    return redirect(url_for("catalog.index"))


@catalog.route("/calibre")
@login_required_if_no_ano
def calibre():
    sort_param = (request.args.get("sort") or "stored").lower()
    return redirect(url_for(
        "web.books_list", data="newest", sort_param=sort_param, book_id=1,
        page=max(request.args.get("page", 1, type=int), 1),
    ))
