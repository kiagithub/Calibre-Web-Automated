# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import pytest
from flask import Blueprint, Flask, g, jsonify, request

from cps import usermanagement
from cps.search import search


REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeUser:
    is_authenticated = True
    is_anonymous = False
    id = 1
    locale = "en"
    name = "Test user"


@pytest.fixture
def search_app(monkeypatch):
    app = Flask("search-test")
    app.config.update(SECRET_KEY="test", TESTING=True)

    catalog = Blueprint("catalog", __name__)

    @catalog.route("/books/")
    def index():
        return jsonify({"q": request.args.get("q", "")})

    app.register_blueprint(catalog)
    app.register_blueprint(search)

    @app.before_request
    def authenticate():
        g.flask_httpauth_user = FakeUser()

    monkeypatch.setattr(usermanagement.config, "config_allow_reverse_proxy_header_login", False, raising=False)
    monkeypatch.setattr(usermanagement.config, "config_anonbrowse", 0, raising=False)
    yield app


@pytest.mark.unit
def test_global_search_redirects_to_combined_book_catalog(search_app):
    response = search_app.test_client().get("/search", query_string={"query": "Blood Meridian"})

    assert response.status_code == 302
    assert response.location.endswith("/books/?q=Blood+Meridian")


@pytest.mark.unit
def test_global_search_placeholder_does_not_claim_calibre_only():
    layout = (REPO_ROOT / "cps" / "templates" / "layout.html").read_text(encoding="utf-8")

    assert 'placeholder="{{_(\'Search books\')}}"' in layout
    assert "Search Calibre books" not in layout
