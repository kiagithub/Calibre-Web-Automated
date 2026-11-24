# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timezone

import pytest
from flask import Flask, g, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cps import ub, usermanagement
from cps.external_books.models import ExternalBook
from cps.media.stats import collect_media_stats
from cps.media_api.auth import hash_key
from cps.media_api.models import ApiKey
from cps.media_api.routes import media_api
from cps.movie_library.models import Movie
from cps.wishlist.models import MediaRequest


class FakeUser:
    id = 1
    is_authenticated = True
    is_anonymous = False
    name = "Test user"
    email = "test@example.com"
    locale = "en"

    def role_admin(self):
        return False

    def role_edit(self):
        return True

    def role_delete_books(self):
        return True

    def role_upload(self):
        return False


@pytest.fixture
def media_api_app(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    ub.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(ub, "session", session)
    session.add(ub.User(id=1, name="test", email="test@example.com", role=0))
    session.commit()
    monkeypatch.setattr(
        "cps.media_api.routes.render_title_template",
        lambda template, **context: jsonify(template=template, raw_key=context.get("raw_key")),
    )
    monkeypatch.setattr(usermanagement.config, "config_allow_reverse_proxy_header_login", False, raising=False)
    monkeypatch.setattr(usermanagement.config, "config_anonbrowse", 0, raising=False)

    app = Flask("media-api-test")
    app.config.update(SECRET_KEY="test", TESTING=True)
    app.register_blueprint(media_api)
    for endpoint, rule in (
        ("external_books.detail", "/stub/external-books/<int:book_id>"),
        ("external_books.cover", "/stub/external-books/<int:book_id>/cover"),
        ("movies.detail", "/stub/movies/<int:movie_id>"),
        ("movies.poster", "/stub/movies/<int:movie_id>/poster"),
        ("movies.backdrop", "/stub/movies/<int:movie_id>/backdrop"),
    ):
        app.add_url_rule(rule, endpoint=endpoint, view_func=lambda **kwargs: "")
    app.config["TEST_USER"] = FakeUser()

    @app.before_request
    def authenticate():
        g.flask_httpauth_user = app.config["TEST_USER"]

    yield app, session
    session.close()
    engine.dispose()


def seed(session):
    book = ExternalBook(
        title="Dune", media_type="physical", isbn_13="9780441172719",
        created_at=datetime.now(timezone.utc),
    )
    book.authors = ["Frank Herbert"]
    audiobook = ExternalBook(
        title="Dune Messiah", media_type="audiobook", narrator="Simon Vance",
        duration_minutes=600, audio_format="M4B",
    )
    audiobook.authors = ["Frank Herbert"]
    movie = Movie(
        title="Arrival", media_format="Blu-ray", release_date="2016-11-11",
        tmdb_id=329865, created_at=datetime.now(timezone.utc),
        tagline="Why are they here?", collection_name="SciFi Classics",
        vote_count=16420, trailer_url="https://www.youtube.com/watch?v=trailer456",
        backdrop_filename="backdrop.jpg",
    )
    request = MediaRequest(user_id=1, content_type="book", title="Hyperion")
    request.authors = ["Dan Simmons"]
    session.add_all([book, audiobook, movie, request])
    session.commit()
    return book, audiobook, movie, request


def api_key(session, token="secret-token", revoked=False):
    key = ApiKey(
        user_id=1,
        name="test",
        key_hash=hash_key(token),
        readonly=True,
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    session.add(key)
    session.commit()
    return key


@pytest.mark.unit
class TestMediaApi:
    def test_requires_a_valid_key(self, media_api_app):
        app, _session = media_api_app
        client = app.test_client()
        assert client.get("/api/media/books").status_code == 401
        assert client.get(
            "/api/media/books", headers={"X-Api-Key": "wrong"}
        ).status_code == 401

    def test_books_and_movies_are_serialized(self, media_api_app):
        app, session = media_api_app
        seed(session)
        api_key(session)
        client = app.test_client()
        headers = {"Authorization": "Bearer secret-token"}

        books = client.get("/api/media/books", headers=headers).get_json()
        movies = client.get("/api/media/movies", headers=headers).get_json()

        assert books["total"] == 2
        assert {book["title"] for book in books["books"]} == {"Dune", "Dune Messiah"}
        assert movies["total"] == 1
        movie_item = movies["movies"][0]
        assert movie_item["tmdb_id"] == 329865
        assert movie_item["tagline"] == "Why are they here?"
        assert movie_item["collection_name"] == "SciFi Classics"
        assert movie_item["vote_count"] == 16420
        assert movie_item["trailer_url"] == "https://www.youtube.com/watch?v=trailer456"
        assert movie_item["backdrop_url"].endswith("/backdrop")

    def test_filters_and_search(self, media_api_app):
        app, session = media_api_app
        seed(session)
        api_key(session)
        client = app.test_client()
        headers = {"X-Api-Key": "secret-token"}

        audiobooks = client.get(
            "/api/media/books?media_type=audiobook", headers=headers
        ).get_json()
        assert audiobooks["total"] == 1
        assert audiobooks["books"][0]["narrator"] == "Simon Vance"

        search = client.get("/api/media/search?q=dune", headers=headers).get_json()
        assert {book["title"] for book in search["books"]} == {"Dune", "Dune Messiah"}

    def test_stats_counts(self, media_api_app):
        app, session = media_api_app
        seed(session)
        api_key(session)
        stats = app.test_client().get(
            "/api/media/stats", headers={"X-Api-Key": "secret-token"}
        ).get_json()

        assert stats["books"]["total"] == 2
        assert stats["books"]["by_media_type"]["audiobook"] == 1
        assert stats["movies"]["total"] == 1
        assert stats["requests"]["by_status"]["pending"] == 1

    def test_revoked_key_is_rejected(self, media_api_app):
        app, session = media_api_app
        api_key(session, revoked=True)
        response = app.test_client().get(
            "/api/media/books", headers={"X-Api-Key": "secret-token"}
        )
        assert response.status_code == 401

    def test_stats_service_reports_recent_books(self, media_api_app):
        _app, session = media_api_app
        seed(session)
        stats = collect_media_stats()
        assert stats["books"]["added_7d"] == 2
        assert stats["movies"]["added_7d"] == 1


@pytest.mark.unit
def test_api_key_management_creates_and_revokes_a_key(media_api_app):
    app, session = media_api_app
    client = app.test_client()

    response = client.get("/account/api-keys")
    assert response.status_code == 200
    assert response.get_json()["template"] == "media_api/keys.html"

    response = client.post("/account/api-keys", data={"name": "Dashboard"})
    assert response.status_code == 200
    raw_key = response.get_json()["raw_key"]
    assert raw_key
    key = session.query(ApiKey).one()
    assert key.key_hash == hash_key(raw_key)
    assert key.revoked_at is None

    response = client.post(f"/account/api-keys/{key.id}/revoke")
    assert response.status_code == 302
    session.refresh(key)
    assert key.revoked_at is not None
