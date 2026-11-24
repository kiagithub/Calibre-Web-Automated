# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from types import SimpleNamespace

import pytest

from cps.metadata_provider import hardcover


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"data": {"search": {"results": {"hits": []}}}}


@pytest.mark.unit
def test_hardcover_authorization_is_per_request(monkeypatch):
    calls = []
    monkeypatch.setattr(hardcover.Hardcover, "HEADERS", hardcover.Hardcover.HEADERS.copy())
    hardcover.Hardcover.HEADERS.pop("Authorization", None)
    user = SimpleNamespace(hardcover_token="first-token")
    monkeypatch.setattr(hardcover, "current_user", user)

    def post(url, **kwargs):
        calls.append(kwargs)
        return FakeResponse()

    monkeypatch.setattr(hardcover.requests, "post", post)
    provider = hardcover.Hardcover()
    assert provider.search("Arrival") == []
    user.hardcover_token = "second-token"
    assert provider.search("Arrival") == []

    assert calls[0]["headers"]["Authorization"] == "Bearer first-token"
    assert calls[1]["headers"]["Authorization"] == "Bearer second-token"
    assert calls[0]["headers"] is not calls[1]["headers"]
    assert calls[0]["headers"]["Authorization"] == "Bearer first-token"
    assert "Authorization" not in hardcover.Hardcover.HEADERS
