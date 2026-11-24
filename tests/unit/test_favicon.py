# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "cps" / "static"


def _png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def test_favicon_svg_uses_the_brand_mark():
    svg = (STATIC / "favicon.svg").read_text(encoding="utf-8")

    assert 'viewBox="0 0 64 64"' in svg
    assert "#3CB39D" in svg
    assert "#DF9F55" in svg
    assert "M10 19" in svg and "M54 19" in svg


def test_ico_has_multiple_sizes():
    data = (STATIC / "favicon.ico").read_bytes()

    assert data[:4] == b"\x00\x00\x01\x00"
    count = int.from_bytes(data[4:6], "little")
    assert count >= 5
    sizes = set()
    for index in range(count):
        entry = data[6 + index * 16: 6 + (index + 1) * 16]
        sizes.add((entry[0] or 256, entry[1] or 256))

    assert (16, 16) in sizes
    assert (32, 32) in sizes
    assert (256, 256) in sizes


def test_png_app_icons_follow_the_expected_dimensions():
    assert _png_size(STATIC / "icon.png") == (800, 800)
    assert _png_size(STATIC / "apple-touch-icon.png") == (180, 180)


def test_templates_prefer_svg_with_ico_and_apple_touch_fallbacks():
    layout = (REPO_ROOT / "cps" / "templates" / "layout.html").read_text(encoding="utf-8")
    read = (REPO_ROOT / "cps" / "templates" / "read.html").read_text(encoding="utf-8")

    for template in (layout, read):
        assert "favicon.svg" in template
        assert "apple-touch-icon.png" in template
        assert "favicon.ico" in template
        assert template.index("favicon.svg") < template.index("favicon.ico")
