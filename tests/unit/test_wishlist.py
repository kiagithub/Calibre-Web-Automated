# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from flask import Flask, g, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cps import ub, usermanagement
from cps.external_books.models import ExternalBook
from cps.wishlist import notifications, service
from cps.wishlist.models import MediaRequest
from cps.wishlist.routes import wishlist


class FakeUser:
    is_authenticated = True
    is_anonymous = False
    id = 1
    name = "Test user"
    email = "test@example.com"
    locale = "en"

    def __init__(self, edit=True, admin=False):
        self.edit = edit
        self.admin = admin

    def role_admin(self):
        return self.admin

    def role_edit(self):
        return self.edit

    def role_delete_books(self):
        return True

    def role_upload(self):
        return False


@pytest.fixture
def wishlist_app(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    ub.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(ub, "session", session)
    events = []
    monkeypatch.setattr(
        notifications, "notify_request", lambda event, entry, note="": events.append(event)
    )
    monkeypatch.setattr(
        "cps.wishlist.routes.render_title_template",
        lambda template, **context: jsonify(
            template=template,
            entries=[entry.title for entry in context.get("entries", [])],
            errors=context.get("errors", []),
            total=context.get("total"),
        ),
    )
    monkeypatch.setattr(usermanagement.config, "config_allow_reverse_proxy_header_login", False, raising=False)
    monkeypatch.setattr(usermanagement.config, "config_anonbrowse", 0, raising=False)

    app = Flask("wishlist-test")
    app.config.update(SECRET_KEY="test", TESTING=True)
    app.register_blueprint(wishlist)
    user = FakeUser()
    app.config["TEST_USER"] = user

    @app.before_request
    def authenticate():
        g.flask_httpauth_user = app.config["TEST_USER"]

    yield app, session, user, events
    session.close()
    engine.dispose()


def request_data(**overrides):
    data = {
        "content_type": "book",
        "title": "Dune",
        "authors": "Frank Herbert",
        "isbn_13": "9780441172719",
        "note": "Prefer the deluxe edition.",
    }
    data.update(overrides)
    return data


@pytest.mark.unit
class TestWishlist:
    def test_user_can_create_and_cancel_a_request(self, wishlist_app):
        app, session, _user, events = wishlist_app
        client = app.test_client()

        response = client.post("/wishlist/new", data=request_data())

        assert response.status_code == 302
        entry = session.query(MediaRequest).one()
        assert entry.status == "pending"
        assert entry.authors == ["Frank Herbert"]
        assert entry.identifiers["isbn_13"] == "9780441172719"
        assert events == ["created"]

        response = client.post(f"/wishlist/{entry.id}/cancel")
        assert response.status_code == 302
        assert entry.status == "cancelled"

    def test_request_item_is_idempotent(self, wishlist_app):
        app, session, _user, events = wishlist_app
        client = app.test_client()
        payload = {
            "content_type": "book",
            "title": "Dune",
            "authors": ["Frank Herbert"],
            "isbn_13": "9780441172719",
        }

        first = client.post("/wishlist/request", json=payload)
        second = client.post("/wishlist/request", json=payload)

        assert first.get_json()["created"] is True
        assert second.get_json()["created"] is False
        assert session.query(MediaRequest).count() == 1
        assert events == ["created"]

    def test_admin_can_approve_reject_and_reopen(self, wishlist_app):
        app, session, _user, events = wishlist_app
        client = app.test_client()
        client.post("/wishlist/new", data=request_data())
        entry = session.query(MediaRequest).one()

        client.post(f"/wishlist/{entry.id}/approve", data={"admin_note": "Ordered"})
        assert entry.status == "approved"
        assert entry.admin_note == "Ordered"

        client.post(f"/wishlist/{entry.id}/reject", data={"admin_note": "Unavailable"})
        assert entry.status == "rejected"

        client.post(f"/wishlist/{entry.id}/reopen")
        assert entry.status == "pending"
        assert events == ["created", "approved", "rejected"]

    def test_edit_permission_is_required_to_moderate(self, wishlist_app):
        app, session, user, _events = wishlist_app
        client = app.test_client()
        client.post("/wishlist/new", data=request_data())
        entry = session.query(MediaRequest).one()

        user.edit = False
        assert client.post(f"/wishlist/{entry.id}/approve").status_code == 403
        assert entry.status == "pending"

    def test_pending_limit_is_enforced(self, wishlist_app, monkeypatch):
        app, session, _user, _events = wishlist_app
        monkeypatch.setattr(service, "MAX_PENDING_REQUESTS", 1)
        client = app.test_client()
        client.post("/wishlist/new", data=request_data(title="First"))

        response = client.post("/wishlist/new", data=request_data(title="Second"))

        assert response.status_code == 200
        assert any("open requests" in error for error in response.get_json()["errors"])
        assert session.query(MediaRequest).count() == 1

    def test_fulfill_links_the_created_book(self, wishlist_app):
        app, session, user, _events = wishlist_app
        client = app.test_client()
        client.post("/wishlist/new", data=request_data())
        entry = session.query(MediaRequest).one()
        book = ExternalBook(title="Dune", media_type="physical")
        session.add(book)
        session.commit()

        service.fulfill_request(entry, user.id, external_book_id=book.id)

        assert entry.status == "fulfilled"
        assert entry.fulfilled_external_book_id == book.id
