import re
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPO_ROOT / "cps" / "templates"
EXTERNAL_TEMPLATES = TEMPLATE_ROOT / "external_books"


def template_environment():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_ROOT)),
        autoescape=select_autoescape(("html", "xml")),
    )


def test_external_book_templates_are_valid_jinja():
    environment = template_environment()
    for path in (
        TEMPLATE_ROOT / "components" / "media_card.html",
        EXTERNAL_TEMPLATES / "index.html",
        EXTERNAL_TEMPLATES / "detail.html",
        EXTERNAL_TEMPLATES / "form.html",
    ):
        environment.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_media_card_has_one_detail_link_and_a_lazy_sized_cover():
    card = SimpleNamespace(
        title="A <Book>",
        byline="An Author",
        cover_url="/covers/1",
        detail_url="/external-books/1",
        badge="Physical",
        location="Shelf A",
        source="external",
        id=1,
        state="Watched",
    )
    rendered = template_environment().get_template("components/media_card.html").module.media_card(card)

    assert rendered.count("<a ") == 1
    assert 'class="media-card"' in rendered
    assert 'class="media-card-link" href="/external-books/1"' in rendered
    assert 'alt="" loading="lazy" width="200" height="300"' in rendered
    assert "A &lt;Book&gt;" in rendered
    assert "An Author" in rendered
    assert "Shelf A" in rendered
    assert 'data-source="external"' in rendered
    assert 'class="media-card-state"' in rendered
    for forbidden_class in ("book", "session", "discover", "book-cover-link"):
        assert f'class="{forbidden_class}"' not in rendered


def test_external_book_form_contains_all_fields_and_separate_forms():
    template = (EXTERNAL_TEMPLATES / "form.html").read_text(encoding="utf-8")
    names = set(re.findall(r'name="([^"]+)"', template))
    expected = {
        "title", "authors", "description", "publisher", "published_date", "series",
        "series_index", "languages", "page_count", "media_type", "binding", "edition",
        "location", "condition", "date_acquired", "personal_rating", "notes", "isbn_10",
        "isbn_13", "asin", "tags", "cover", "remove_cover", "metadata_provider",
        "metadata_id", "metadata_url", "metadata_selected", "cover_url", "csrf_token",
    }
    assert expected <= names

    provider_start = template.index('<form class="external-books-metadata-search-form"')
    provider_end = template.index("</form>", provider_start)
    manual_start = template.index('<form method="post" enctype="multipart/form-data"')
    manual_end = template.index("</form>", manual_start)
    delete_start = template.rindex('<form method="post" action=')
    assert provider_end < manual_start
    assert manual_end < delete_start
    assert 'role="status" aria-live="polite"' in template
    assert 'class="external-books-metadata-results-heading" tabindex="-1"' in template
    assert 'data-cover-url=' in template
    assert 'data-generic-cover=' in template


def test_external_book_metadata_js_uses_safe_dom_and_shared_skeleton():
    script = (REPO_ROOT / "cps" / "static" / "js" / "external_books.js").read_text(encoding="utf-8")

    assert "new URLSearchParams({query: query})" in script
    assert '"X-CSRFToken"' in script
    assert "new DOMParser().parseFromString" in script
    assert 'querySelectorAll("script, style")' in script
    assert ".innerHTML" not in script
    assert "metadataSearch.init({" in script
    assert 'setField("tags"' not in script
    assert 'setField("media_type"' not in script
    assert 'setField("cover",' not in script
    assert 'setField("cover_url", remoteCover(book.cover))' in script
    assert 'return /^https?:\\/\\//i.test(url) ? url : "";' in script
    assert 'setField("metadata_selected", "1")' in script
    assert script.startswith("(function ()")


def test_shared_metadata_search_skeleton_owns_fetch_status_and_focus():
    script = (REPO_ROOT / "cps" / "static" / "js" / "metadata_search.js").read_text(encoding="utf-8")

    assert 'credentials: "same-origin"' in script
    assert 'response.headers.get("X-Metadata-Partial") === "true"' in script
    assert script.count("resultsHeading.focus();") == 2
    assert ".innerHTML" not in script
    assert "global.CWA.metadataSearch = {element: element, init: init}" in script


def test_both_metadata_search_pages_use_the_shared_skeleton():
    movies = (REPO_ROOT / "cps" / "static" / "js" / "movies.js").read_text(encoding="utf-8")
    books = (REPO_ROOT / "cps" / "static" / "js" / "external_books.js").read_text(encoding="utf-8")

    assert "metadataSearch.init({" in movies
    assert "metadataSearch.init({" in books
    assert "function initMetadataSearch()" in movies
    assert "function initMetadataSearch()" in books


def test_metadata_search_templates_load_shared_skeleton_first():
    pages = [
        (TEMPLATE_ROOT / "movies" / "form.html", "movies.js"),
        (EXTERNAL_TEMPLATES / "form.html", "external_books.js"),
        (EXTERNAL_TEMPLATES / "detail.html", "external_books.js"),
    ]
    for path, page_script in pages:
        template = path.read_text(encoding="utf-8")
        assert template.index("js/metadata_search.js") < template.index(f"js/{page_script}")


def test_external_book_metadata_results_show_lazy_cover_thumbnails():
    script = (REPO_ROOT / "cps" / "static" / "js" / "external_books.js").read_text(encoding="utf-8")

    assert 'panel.dataset.coverUrl + "?url=" + encodeURIComponent(cover)' in script
    assert 'element("img", "external-books-metadata-result-cover")' in script
    assert 'cover.loading = "lazy"' in script
    assert 'cover.decoding = "async"' in script
    assert ".innerHTML" not in script


def test_metadata_thumbnail_css_overrides_the_legacy_container_image_rule():
    css = (REPO_ROOT / "cps" / "static" / "css" / "media.css").read_text(encoding="utf-8")

    assert ".external-books-page .external-books-metadata-result-cover" in css
    assert "max-width: 60px" in css
    assert "box-shadow: none" in css
