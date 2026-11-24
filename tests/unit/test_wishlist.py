# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from flask import Flask, g, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cps import ub, usermanagement
from cps.external_books.models import ExternalBook
from cps.media.links import library_links
from cps.wishlist import hardcover_sync, notifications, service
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

    def test_per_user_policy_blocks_requests(self, wishlist_app):
        app, session, _user, _events = wishlist_app
        session.add(ub.User(
            id=1, name="Test user", email="test@example.com", role=0,
            view_settings={"wishlist": {"requests_allowed": False}},
        ))
        session.commit()

        response = app.test_client().post("/wishlist/new", data=request_data())

        assert response.status_code == 200
        assert any("disabled" in error for error in response.get_json()["errors"])
        assert session.query(MediaRequest).count() == 0

    def test_admin_policy_page_updates_user_settings(self, wishlist_app):
        app, session, _user, _events = wishlist_app
        user = ub.User(id=1, name="Test user", email="test@example.com", role=0)
        session.add(user)
        session.commit()

        response = app.test_client().post("/wishlist/policies", data={
            "max_pending_1": "5",
            "requests_allowed_1": "on",
        })

        assert response.status_code == 302
        session.refresh(user)
        assert user.view_settings["wishlist"]["max_pending"] == 5
        assert user.view_settings["wishlist"]["requests_allowed"] is True

    def test_notification_preference_can_be_disabled(self, wishlist_app):
        app, session, _user, _events = wishlist_app
        user = ub.User(id=1, name="Test user", email="test@example.com", role=0)
        session.add(user)
        session.commit()

        response = app.test_client().post("/wishlist/notifications", data={})

        assert response.status_code == 302
        session.refresh(user)
        assert user.view_settings["wishlist_notifications"] is False

    def test_hardcover_sync_creates_and_deduplicates_requests(self, wishlist_app, monkeypatch):
        app, session, _user, _events = wishlist_app
        user = ub.User(
            id=1, name="Test user", email="test@example.com", role=0,
            hardcover_token="token",
        )
        session.add(user)
        session.commit()
        monkeypatch.setattr(
            hardcover_sync, "fetch_shelf_books",
            lambda token, status_id: [{"id": 42, "title": "Dune", "authors": ["Frank Herbert"]}],
        )
        monkeypatch.setattr(hardcover_sync, "_owned", lambda *args: False)

        first = hardcover_sync.sync_user(user)
        second = hardcover_sync.sync_user(user)

        assert first["created"] == 1
        assert second["created"] == 0
        entry = session.query(MediaRequest).one()
        assert entry.metadata_provider == "hardcover"
        assert entry.metadata_id == "42"
        assert entry.authors == ["Frank Herbert"]

    def test_fetch_shelf_books_parses_contributions_and_falls_back(self, monkeypatch):
        calls = []

        class FakeResponse:
            def __init__(self, data, status_code=200):
                self._data = data
                self.status_code = status_code

            def raise_for_status(self):
                pass

            def json(self):
                return self._data

        def fake_post(url, json=None, **kwargs):
            query = (json or {}).get("query", "")
            calls.append(query)
            if "contributions" in query:
                return FakeResponse({
                    "data": {
                        "me": [{
                            "user_books": [{
                                "book": {
                                    "id": 99,
                                    "title": "Hyperion",
                                    "contributions": [{"author": {"name": "Dan Simmons"}}],
                                }
                            }]
                        }]
                    }
                })
            return FakeResponse({
                "data": {
                    "me": [{
                        "user_books": [{
                            "book": {
                                "id": 100,
                                "title": "Foundation",
                            }
                        }]
                    }]
                }
            })

        monkeypatch.setattr(hardcover_sync.requests, "post", fake_post)

        books = hardcover_sync.fetch_shelf_books("fake_token", 1)
        assert len(books) == 1
        assert books[0]["title"] == "Hyperion"
        assert books[0]["authors"] == ["Dan Simmons"]

        # Now test fallback when contributions query fails
        calls.clear()

        def fake_post_with_fallback(url, json=None, **kwargs):
            query = (json or {}).get("query", "")
            calls.append(query)
            if "contributions" in query:
                # Return GraphQL error simulating schema incompatibility
                return FakeResponse({"errors": [{"message": "Cannot query field 'contributions'"}]})
            return FakeResponse({
                "data": {
                    "me": [{
                        "user_books": [{
                            "book": {
                                "id": 101,
                                "title": "Solaris",
                            }
                        }]
                    }]
                }
            })

        monkeypatch.setattr(hardcover_sync.requests, "post", fake_post_with_fallback)
        fallback_books = hardcover_sync.fetch_shelf_books("fake_token", 1)
        assert len(fallback_books) == 1
        assert fallback_books[0]["title"] == "Solaris"
        assert fallback_books[0]["authors"] == []
        assert len(calls) == 2  # Attempted SHELF_QUERY, then fell back to SHELF_QUERY_SIMPLE

    def test_library_links_are_validated(self, monkeypatch):
        monkeypatch.setenv("PLEX_URL", "https://plex.example")
        monkeypatch.setenv("JELLYFIN_URL", "javascript:alert(1)")
        links = library_links()
        assert [link["label"] for link in links] == ["Plex"]

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
