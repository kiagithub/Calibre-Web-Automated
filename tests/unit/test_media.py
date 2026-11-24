# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from types import SimpleNamespace

import requests
import pytest
from flask import Flask

from cps import helper
from cps.cw_advocate.exceptions import UnacceptableAddressException
from cps.media import (
    ArtworkStore,
    ImageDownloadError,
    ImageRedirectError,
    ImageTooLargeError,
    InvalidImageError,
    download_image,
)
from cps.media.permissions import media_permissions

JPEG = b"\xff\xd8\xff" + b"test-image"


@pytest.mark.unit
@pytest.mark.parametrize("authenticated,edit,delete,admin,expected", [
    (True, True, False, False, {"can_edit_media": True, "can_delete_media": False}),
    (True, False, True, False, {"can_edit_media": False, "can_delete_media": True}),
    (True, False, False, True, {"can_edit_media": True, "can_delete_media": True}),
    (False, True, True, False, {"can_edit_media": False, "can_delete_media": False}),
])
def test_media_permissions_are_shared_booleans(authenticated, edit, delete, admin, expected):
    user = SimpleNamespace(
        is_authenticated=authenticated,
        role_edit=lambda: edit,
        role_delete_books=lambda: delete,
        role_admin=lambda: admin,
    )
    assert media_permissions(user) == expected


class FakeResponse:
    def __init__(self, data=JPEG, *, status=200, headers=None):
        self.data = data
        self.status_code = status
        self.headers = headers or {}
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, size):
        for index in range(0, len(self.data), size):
            yield self.data[index:index + size]

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


@pytest.mark.unit
class TestImageDownloader:
    def test_rejects_redirect_and_closes_response(self):
        response = FakeResponse(status=302)
        session = FakeSession(response)
        with pytest.raises(ImageRedirectError):
            download_image("https://example.com/cover.jpg", max_bytes=1024, session=session)
        assert response.closed
        assert session.calls[0][1]["allow_redirects"] is False
        assert session.calls[0][1]["timeout"] == (10, 30)

    def test_rejects_oversized_content_length_before_streaming(self):
        response = FakeResponse(headers={"content-length": "1025"})
        with pytest.raises(ImageTooLargeError):
            download_image("https://example.com/cover.jpg", max_bytes=1024, session=FakeSession(response))
        assert response.closed

    def test_rejects_oversized_stream_without_content_length(self):
        response = FakeResponse(data=JPEG + b"x" * 1024)
        with pytest.raises(ImageTooLargeError):
            download_image("https://example.com/cover.jpg", max_bytes=1024, session=FakeSession(response))
        assert response.closed

    def test_rejects_invalid_image_and_closes_response(self):
        response = FakeResponse(data=b"<svg onload=alert(1)>")
        with pytest.raises(InvalidImageError):
            download_image("https://example.com/cover.jpg", max_bytes=1024, session=FakeSession(response))
        assert response.closed

    def test_allowlist_rejection_makes_no_request(self):
        session = FakeSession(FakeResponse())
        with pytest.raises(ImageDownloadError, match="not allowed"):
            download_image(
                "https://example.com/cover.jpg", max_bytes=1024, session=session,
                url_validator=lambda url: url.startswith("https://images.example.com/"),
            )
        assert session.calls == []

    def test_injected_session_returns_validated_bytes_and_closes(self):
        response = FakeResponse(headers={"content-type": "image/jpeg"})
        downloaded = download_image(
            "https://example.com/cover.jpg", max_bytes=1024,
            session=FakeSession(response), timeout=(1, 2),
        )
        assert downloaded.data == JPEG
        assert downloaded.extension == "jpg"
        assert downloaded.content_type == "image/jpeg"
        assert response.closed


@pytest.mark.unit
class TestArtworkStore:
    def test_stages_unique_images_and_validates_basenames(self, tmp_path):
        store = ArtworkStore(tmp_path / "app.db", "movie_covers")
        first = store.stage(JPEG, "jpg", "movie-1", max_bytes=1024)
        second = store.stage(JPEG, "jpg", "movie-1", max_bytes=1024)
        assert first != second
        assert store.root == str(tmp_path / "movie_covers")
        assert (tmp_path / "movie_covers" / first).read_bytes() == JPEG
        with pytest.raises(ValueError, match="basename|filename"):
            store.path("../outside.jpg")
        store.discard(first)
        store.delete(second)
        assert not (tmp_path / "movie_covers" / first).exists()
        assert not (tmp_path / "movie_covers" / second).exists()

    def test_stage_rejects_invalid_or_oversized_data(self, tmp_path):
        store = ArtworkStore(tmp_path / "app.db", "movie_covers")
        with pytest.raises(ValueError):
            store.stage(b"not an image", "jpg", "movie-1", max_bytes=1024)
        with pytest.raises(ValueError):
            store.stage(JPEG, "jpg", "movie-1", max_bytes=2)


@pytest.mark.unit
class TestCoverDownloadCompatibility:
    @pytest.fixture(autouse=True)
    def app_context(self, monkeypatch):
        app = Flask("test")
        monkeypatch.setattr(helper, "_", lambda text, **values: text % values if values else text)
        with app.app_context():
            yield

    def test_uses_advocate_and_preserves_save_cover_response(self, monkeypatch):
        response = FakeResponse(headers={"content-type": "image/jpeg"})
        session = FakeSession(response)
        saved = []
        monkeypatch.setattr(helper, "_get_cover_download_limit", lambda: (1024, 1))
        monkeypatch.setattr(helper.cli_param, "allow_localhost", False)
        monkeypatch.setattr(helper, "use_advocate", True)
        monkeypatch.setattr(helper, "cw_advocate", session)
        monkeypatch.setattr(helper, "save_cover", lambda img, path: saved.append((img, path)) or (True, None))

        assert helper.save_cover_from_url("https://example.com/cover.jpg", "Author/Book") == (True, None)
        assert response.closed
        assert saved[0][0].content == JPEG
        assert saved[0][0].headers["content-type"] == "image/jpeg"
        assert saved[0][1] == "Author/Book"

    def test_local_address_error_keeps_existing_message(self, monkeypatch):
        session = FakeSession(error=UnacceptableAddressException("127.0.0.1"))
        monkeypatch.setattr(helper, "_get_cover_download_limit", lambda: (1024, 1))
        monkeypatch.setattr(helper.cli_param, "allow_localhost", False)
        monkeypatch.setattr(helper, "use_advocate", True)
        monkeypatch.setattr(helper, "cw_advocate", session)

        success, message = helper.save_cover_from_url("http://127.0.0.1/cover.jpg", "Author/Book")
        assert success is False
        assert message == "You are not allowed to access localhost or the local network for cover uploads"

    def test_content_length_limit_keeps_existing_message_and_closes(self, monkeypatch):
        response = FakeResponse(headers={"content-length": "1025"})
        monkeypatch.setattr(helper, "_get_cover_download_limit", lambda: (1024, 1))
        monkeypatch.setattr(helper.cli_param, "allow_localhost", False)
        monkeypatch.setattr(helper, "use_advocate", True)
        monkeypatch.setattr(helper, "cw_advocate", FakeSession(response))

        success, message = helper.save_cover_from_url("https://example.com/cover.jpg", "Author/Book")
        assert success is False
        assert message == "Cover image exceeds maximum size of 1 MB"
        assert response.closed
