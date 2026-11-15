# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_local_env_files_are_ignored_but_example_is_tracked():
    rules = (REPO / ".gitignore").read_text().splitlines()
    assert ".env" in rules
    assert ".env.*" in rules
    assert "!.env.example" in rules


@pytest.mark.unit
def test_tmdb_example_uses_placeholders_not_credentials():
    values = {}
    for line in (REPO / ".env.example").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    assert values["TMDB_READ_ACCESS_TOKEN"] == "your_tmdb_read_access_token_here"
    assert values["TMDB_API_KEY"] == "your_tmdb_api_key_here"
