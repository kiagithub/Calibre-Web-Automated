# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from cps.external_books import thumbnails
from cps.media import ImageDownloadError

JPEG = b"\xff\xd8\xff" + b"test-image"


@pytest.fixture(autouse=True)
def clear_cache():
    thumbnails.clear_thumbnail_cache()
    yield
    thumbnails.clear_thumbnail_cache()


@pytest.mark.unit
class TestCoverUrlPolicy:
    @pytest.mark.parametrize("url", [
        "https://books.google.com/cover.jpg",
        "http://example.test:80/cover.jpg",
        "https://example.test/cover.png?size=large",
    ])
    def test_accepts_bounded_http_urls(self, url):
        assert thumbnails.valid_cover_url(url)

    @pytest.mark.parametrize("url", [
        "",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:pass@example.test/cover.jpg",
        "https://example.test:22/cover.jpg",
        "https://",
        "https://example.test/" + "a" * 2000,
    ])
    def test_rejects_unsafe_urls(self, url):
        assert not thumbnails.valid_cover_url(url)

    def test_google_covers_request_a_preview_sized_image(self):
        source = "https://books.google.com/books/content?id=abc&fife=w800-h900"

        assert thumbnails._thumbnail_source(source).endswith("&fife=w200-h300")
        assert thumbnails._thumbnail_source("https://example.test/cover.jpg") == \
            "https://example.test/cover.jpg"


@pytest.mark.unit
class TestMetadataThumbnail:
    def test_thumbnail_is_cached_by_url(self, monkeypatch):
        calls = []

        def fake_download(url):
            calls.append(url)
            return JPEG, "jpg"

        monkeypatch.setattr(thumbnails, "WandImage", None)
        monkeypatch.setattr(thumbnails, "download_cover", fake_download)
        url = "https://example.test/cover.jpg"

        first = thumbnails.metadata_thumbnail(url)
        second = thumbnails.metadata_thumbnail(url)

        assert first == (JPEG, "image/jpeg")
        assert second == first
        assert calls == [url]

    def test_download_failure_returns_none(self, monkeypatch):
        def fail_download(_url):
            raise ImageDownloadError("Unavailable")

        monkeypatch.setattr(thumbnails, "download_cover", fail_download)

        assert thumbnails.metadata_thumbnail("https://example.test/cover.jpg") is None

    def test_invalid_url_is_not_downloaded(self, monkeypatch):
        calls = []
        monkeypatch.setattr(thumbnails, "download_cover", lambda url: calls.append(url))

        assert thumbnails.metadata_thumbnail("javascript:alert(1)") is None
        assert calls == []
