# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from flask import Blueprint, redirect, request, url_for

from ..media import media_permissions
from ..external_books.models import MEDIA_TYPES
from ..pagination import Pagination
from ..render_template import render_title_template
from ..usermanagement import login_required_if_no_ano
from .read_models import MEDIA_TYPE_LABELS
from .service import available_tags, combined_books

catalog = Blueprint("catalog", __name__, url_prefix="/books")


@catalog.route("/")
@login_required_if_no_ano
def index():
    query_text = request.args.get("q", "").strip()[:200]
    source = request.args.get("source", "all")
    if source not in ("all", "calibre", "external"):
        source = "all"
    media_type = request.args.get("media_type", "").strip()
    if media_type not in MEDIA_TYPES:
        media_type = ""
    tag = request.args.get("tag", "").strip()[:100]
    requested_page = max(request.args.get("page", 1, type=int), 1)
    result = combined_books(
        page=requested_page, per_page=24, query_text=query_text,
        source=source, media_type=media_type, tag=tag,
    )
    filters = {"q": query_text, "source": source, "media_type": media_type, "tag": tag}
    if requested_page != result.page:
        return redirect(url_for("catalog.index", **filters, page=result.page))
    tags = available_tags()
    return render_title_template(
        "catalog/index.html", title=f"Books ({result.total})", page="books",
        entries=result.cards, total=result.total,
        pagination=Pagination(result.page, result.per_page, result.total),
        query_text=query_text, selected_source=source, selected_type=media_type,
        selected_tag=tag, tags=tags,
        types=[(value, MEDIA_TYPE_LABELS[value]) for value in MEDIA_TYPES],
        **media_permissions(),
    )


@catalog.route("/calibre")
@login_required_if_no_ano
def calibre():
    sort_param = (request.args.get("sort") or "stored").lower()
    return redirect(url_for(
        "web.books_list", data="newest", sort_param=sort_param, book_id=1,
        page=max(request.args.get("page", 1, type=int), 1),
    ))
