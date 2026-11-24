# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from flask import Blueprint, Flask, g, jsonify
from flask_babel import Babel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cps import ub, usermanagement, web
from cps.catalog import routes
from cps.catalog.service import CatalogResult
from cps.external_books import routes as external_routes
from cps.jinjia import jinjia


class FakeUser:
    is_authenticated = True
    is_anonymous = False
    id = 1
    locale = "en"
    name = "Test user"
    kindle_mail = ""
    view_settings = None

    def __init__(self, view_settings=None):
        self.view_settings = view_settings or {}

    def role_admin(self):
        return False

    def role_edit(self):
        return True

    def role_delete_books(self):
        return True


@pytest.fixture
def catalog_app(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ub.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(ub, "session", session)
    app = Flask("cps")
    app.config.update(SECRET_KEY="test", TESTING=True)
    app.register_blueprint(routes.catalog)
    app.register_blueprint(external_routes.external_books)
    app.register_blueprint(jinjia)

    # Only the existing Calibre list endpoint is needed for the drill-down redirect.
    dummy_web = Blueprint("web", __name__)
    @dummy_web.route("/<data>/<sort_param>/<book_id>/<int:page>")
    def books_list(**_kwargs):
        return jsonify({})
    app.register_blueprint(dummy_web)

    user = FakeUser()
    @app.before_request
    def authenticate():
        g.flask_httpauth_user = user
    monkeypatch.setattr(usermanagement.config, "config_allow_reverse_proxy_header_login", False, raising=False)
    monkeypatch.setattr(usermanagement.config, "config_anonbrowse", 0, raising=False)
    monkeypatch.setattr(routes, "render_title_template", lambda template, **context: jsonify(
        template=template,
        entries=[entry.title for entry in context.get("entries", [])],
        total=context.get("total"),
        pagination={
            "keyset": getattr(context["pagination"], "keyset", False),
            "prev_url": getattr(context["pagination"], "prev_url", None),
            "next_url": getattr(context["pagination"], "next_url", None),
        } if context.get("pagination") else None,
    ))
    monkeypatch.setattr(routes, "available_tags", lambda: [])
    yield app
    session.close()
    engine.dispose()


@pytest.mark.unit
def test_combined_catalog_route_renders_cards_and_cursor_pagination(catalog_app, monkeypatch):
    result = CatalogResult(
        [SimpleNamespace(title="Book")], total=50, per_page=24,
        next_cursor="next-cursor", has_next=True,
    )
    monkeypatch.setattr(routes, "combined_books", lambda **_kwargs: result)
    response = catalog_app.test_client().get("/books/?q=Arrival&source=all")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["template"] == "catalog/index.html"
    assert payload["entries"] == ["Book"]
    assert payload["total"] == 50
    pagination = payload["pagination"]
    assert pagination["keyset"] is True
    assert pagination["prev_url"] is None
    assert "cursor=next-cursor" in pagination["next_url"]
    assert "dir=next" in pagination["next_url"]
    assert "q=Arrival" in pagination["next_url"]


@pytest.mark.unit
def test_legacy_page_parameter_redirects_to_first_page(catalog_app):
    response = catalog_app.test_client().get(
        "/books/?page=99&q=Arrival&source=external&media_type=kindle&tag=Owned"
    )
    parsed = urlparse(response.location)
    assert response.status_code == 302
    assert parse_qs(parsed.query) == {
        "q": ["Arrival"], "source": ["external"], "media_type": ["kindle"],
        "tag": ["Owned"],
    }


@pytest.mark.unit
def test_combined_catalog_route_forwards_cursor_and_direction(catalog_app, monkeypatch):
    captured = {}

    def fake_combined_books(**kwargs):
        captured.update(kwargs)
        return CatalogResult([], total=0, per_page=24)

    monkeypatch.setattr(routes, "combined_books", fake_combined_books)
    response = catalog_app.test_client().get("/books/?cursor=abc&dir=prev")

    assert response.status_code == 200
    assert captured["cursor"] == "abc"
    assert captured["direction"] == "prev"


@pytest.mark.unit
def test_calibre_drilldown_uses_existing_book_list(catalog_app):
    response = catalog_app.test_client().get("/books/calibre?sort=title&page=2")
    assert response.status_code == 302
    assert response.location.endswith("/newest/title/1/2")


@pytest.mark.unit
def test_combined_catalog_route_applies_user_defaults(catalog_app, monkeypatch):
    captured = {}

    def fake_combined_books(**kwargs):
        captured.update(kwargs)
        return CatalogResult([], total=0, per_page=24)

    monkeypatch.setattr(routes, "combined_books", fake_combined_books)
    monkeypatch.setattr(routes, "catalog_defaults", lambda _user: {"source": "external", "media_type": "kindle"})

    response = catalog_app.test_client().get("/books/")
    assert response.status_code == 200
    assert captured["source"] == "external"
    assert captured["media_type"] == "kindle"


@pytest.mark.unit
def test_combined_catalog_route_explicit_params_override_defaults(catalog_app, monkeypatch):
    captured = {}

    def fake_combined_books(**kwargs):
        captured.update(kwargs)
        return CatalogResult([], total=0, per_page=24)

    monkeypatch.setattr(routes, "combined_books", fake_combined_books)
    monkeypatch.setattr(routes, "catalog_defaults", lambda _user: {"source": "external", "media_type": "kindle"})

    response = catalog_app.test_client().get("/books/?source=calibre&media_type=")
    assert response.status_code == 200
    assert captured["source"] == "calibre"
    assert captured["media_type"] == ""


@pytest.mark.unit
def test_combined_catalog_save_defaults_param(catalog_app, monkeypatch):
    saved = {}

    def fake_set_defaults(_user, defaults):
        saved.update(defaults)
        return True

    monkeypatch.setattr(routes, "set_catalog_defaults", fake_set_defaults)
    monkeypatch.setattr(routes, "combined_books", lambda **_kwargs: CatalogResult([], total=0, per_page=24))

    response = catalog_app.test_client().get("/books/?source=external&media_type=audiobook&save_defaults=1")
    assert response.status_code == 200
    assert saved == {"source": "external", "media_type": "audiobook"}


@pytest.mark.unit
def test_combined_catalog_defaults_post_route(catalog_app, monkeypatch):
    saved = {}

    def fake_set_defaults(_user, defaults):
        saved.update(defaults)
        return True

    monkeypatch.setattr(routes, "set_catalog_defaults", fake_set_defaults)

    response = catalog_app.test_client().post("/books/defaults", data={"source": "calibre", "media_type": ""})
    assert response.status_code == 302
    assert response.location.endswith("/books/")
    assert saved == {"source": "calibre", "media_type": ""}


@pytest.mark.unit
def test_home_uses_combined_recent_sections_and_legacy_page_redirect(monkeypatch):
    app = Flask("cps")
    app.config.update(SECRET_KEY="test", TESTING=True)
    Babel(app)
    app.register_blueprint(web.web)
    user = FakeUser()

    @app.before_request
    def authenticate():
        g.flask_httpauth_user = user

    monkeypatch.setattr(usermanagement.config, "config_allow_reverse_proxy_header_login", False, raising=False)
    monkeypatch.setattr(usermanagement.config, "config_anonbrowse", 0, raising=False)
    monkeypatch.setattr(web, "recent_home", lambda limit: (
        [SimpleNamespace(title="Book")], [SimpleNamespace(title="Movie")], 3, 4
    ))
    monkeypatch.setattr(web, "render_title_template", lambda template, **context: jsonify(
        template=template,
        books=[entry.title for entry in context["books"]],
        movies=[entry.title for entry in context["movies"]],
        total_books=context["total_books"], total_movies=context["total_movies"],
    ))

    response = app.test_client().get("/")
    assert response.get_json() == {
        "template": "catalog/home.html", "books": ["Book"], "movies": ["Movie"],
        "total_books": 3, "total_movies": 4,
    }
    response = app.test_client().get("/page/3?sort=title")
    assert response.status_code == 302
    assert response.location.endswith("/newest/title/1/3")
