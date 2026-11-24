# Home Library

Home Library extends [Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated) with a combined book-and-movie collection. File-backed books continue to use Calibre and CWA's existing ingestion, conversion, metadata, Kobo, and OPDS features. Physical movies and books that live outside Calibre use separate tables in CWA's `app.db`; Calibre's `metadata.db` schema is not changed.

## Included

### Home and navigation

- Home has independent **Books** and **Movies** rows with recent items and source-specific detail links.
- **Books** combines Calibre and personal records in a recent-first catalog with cursor-based Previous/Next pagination. Users can save default source and personal book type preferences via **Save as default**. Numbered page jumps are not offered; legacy `?page=N` links redirect to the first page.
- **Calibre library** retains the existing Calibre lists, sorting, filters, file actions, shelves, and specialized views.
- **Personal books** provides dedicated management for records without Calibre files.
- **Movies** retains the existing physical-movie shelf.
- The sidebar emphasizes Home, Books, and Movies. Secondary book destinations and shelves remain available in keyboard-native collapsible groups, with existing visibility preferences preserved.
- The global search box searches the combined book catalog: Calibre files and personal books. Movie search remains on the Movies page.
- Shared cards use one detail link, consistent 2:3 artwork, responsive grids, visible keyboard focus, and aligned controls.
- Movie, personal-book, and shared pages use grouped selectors in `cps/static/css/media.css`; component-specific overrides stay scoped to their variant.
- The application favicon is a teal book-and-play mark with SVG, multi-size ICO, and Apple touch assets.
- Existing Calibre quick actions use native Read, read-status, Edit, and Send buttons outside the cover link. They work with keyboard and touch instead of depending on mouse coordinates or hover alone.
- Legacy `/page/<n>` book links redirect to the existing Calibre newest-book list. Query-string pagination preserves filters and no longer reuses the old page number.

### Personal books

Personal books catalog one owned edition/copy per record. ISBN and provider identifiers are deliberately non-unique, so a physical copy and a Kindle copy—or multiple physical copies—can coexist.

Supported types:

- **Physical**
- **Kindle**
- **Other digital**
- **Audiobook**

Records can contain:
- title, authors, plain-text description, publisher, publication date, series/index, languages, and page count;
- audiobook narrator, duration, audio format (M4B, MP3, Other), and abridged status;
- free-form tags with Unicode/case-insensitive normalization and deduplication;
- optional binding, edition, location, condition, acquisition date, collection-wide rating, and notes;
- ISBN-10, ISBN-13, ASIN, metadata provider/ID/source URL, and a local cover.

Manual add/edit/delete and custom JPEG/PNG/WebP cover uploads work without online metadata. Online search reuses CWA's existing enabled book providers, including Google Books and other configured sources. Selecting a result fills the visible form for review before saving; there is no new provider hierarchy or automatic Kindle download/account integration.

Enabled providers run side by side. The search responds shortly after the first sources answer, giving near-simultaneous providers a short grace window, and never waits longer than `CWA_METADATA_SEARCH_TIMEOUT` seconds (default 10). Providers still running after that are left out and the response is marked `X-Metadata-Partial`, so one slow source cannot delay the whole list. Complete result sets are cached in memory for five minutes, scoped to the query, locale, user, and enabled-provider set.

Every result shows a small cover thumbnail beside its details. Thumbnails load lazily through a bounded server-side route, use the same Advocate/local-address policy and image checks as saved covers, are downscaled to thumbnail size, and are cached in memory. Applying metadata still records the provider's full cover URL; the thumbnail is only a preview.

Results already in the library carry an **In library** badge naming the source (Calibre, Personal, or Audiobook), and a **Hide owned** toggle filters them out. Providers are deduplicated by provider ID, ISBN-10/13, or normalized title plus author, and Open Library is included as a free provider.

Movie and personal-book metadata search share the fetch, status, error, and focus lifecycle in `cps/static/js/metadata_search.js`; each keeps its own request format and result rendering.

Metadata updates preserve the owned-copy fields, media type, personal tags, location, condition, acquisition details, rating, and notes. Provider tags are suggestions rather than silent replacements.

Records and ratings are shared across library users, matching the movie collection. Viewing follows the normal login/anonymous policy; add/edit and metadata changes require edit permission, deletion requires delete permission, and writes use CSRF protection. Upload permission is not required for a metadata-only record.

### Wishlist and requests

- Signed-in users can request books, audiobooks, or movies from **Wishlist** (or the **Request** button on a metadata result).
- Requests move through `pending`, `approved`, `rejected`, `fulfilled`, and `cancelled`; users can cancel their own open requests and admins/editors can approve, reject, reopen, or fulfil them.
- **Fulfil** opens the existing Add Book or Add Movie form with the request metadata prefilled; saving the record marks the request fulfilled and links the new item.
- Each user can have up to 20 open requests by default. Duplicate open requests for the same title are collapsed instead of creating a second row.
- Email notifications are sent when mail is configured: new requests to admins, and approval/rejection/fulfilment decisions to the requester. Users can opt out from **Notifications** in the profile menu.
- **Request policies** lets admins/editors set a per-user open-request limit and disable requests for an individual account.
- Admins can import a Hardcover shelf (**Want to read**, **Currently reading**, or **Read**) into the wishlist with **Sync now**. The importer fetches book titles and contributors, skips books already owned or already requested, and creates enriched requests. Set `HARDCOVER_SYNC_ENABLED=true` to run it on an interval instead.

### Collection stats and API

- **Collection stats** in the profile menu shows book, audiobook, movie, and wishlist counts, including additions in the last 7 and 30 days.
- **API keys** in the profile menu creates read-only keys. Send a key as `Authorization: Bearer <key>` or `X-Api-Key: <key>`.
- Read-only endpoints: `/api/media/books`, `/api/media/books/<id>`, `/api/media/movies`, `/api/media/movies/<id>`, `/api/media/search`, and `/api/media/stats`.
- Keys are stored hashed, can be revoked, and never expose passwords, file paths, or provider tokens.
- Optional companion-library links appear in the profile menu when `AUDIOBOOKSHELF_URL`, `PLEX_URL`, `JELLYFIN_URL`, or `GRIMMORY_URL` is set. Invalid or non-HTTP(S) URLs are ignored.
- When `AUDIOBOOKSHELF_CHECK_ENABLED=true` is set with `AUDIOBOOKSHELF_URL` and `AUDIOBOOKSHELF_TOKEN`, metadata search checks Audiobookshelf libraries for owned audiobooks, with optional comma-separated `AUDIOBOOKSHELF_LIBRARY_IDS` filtering.

### Movies and shared media safety

- TMDB title/year search, metadata import, and refresh retain the existing movie workflows.
- TMDB search results show an **In library · Movies** badge when the movie is already in the collection, with a **Hide owned** toggle.
- Metadata imports and refreshes extract tagline, franchise/collection name, TMDB vote count, YouTube trailer links, and backdrops alongside director, cast, genres, content rating, and runtime.
- Movie lists sorted by "added" use an indexed `movie.created_at`; startup creates the index idempotently for existing `app.db` files as well as new ones.
- DVD, Blu-ray, 4K UHD, VHS, LaserDisc, Digital, Other, and condition choices are validated server-side.
- Movie and book artwork share bounded image validation, local atomic storage, safe response handling, and upload/download limits. Posters and backdrops are staged before database commits; uncommitted files are cleaned up on error.
- TMDB keeps its HTTPS image-host allowlist for posters and backdrops. Other provider covers use CWA's Advocate/local-address policy, reject redirects, enforce declared and streamed size limits, close responses, and validate image signatures.
- Metadata-search thumbnails accept only HTTP(S) image URLs on standard ports, require edit permission, reuse the same bounded downloader, fall back to the local generic cover on any failure, and are capped at 256 cached images of at most 256 KiB each.
- Movie poster downloads occur before the import write transaction, avoiding network waits while holding a SQLite write transaction.
- Hardcover authorization headers are copied per request rather than mutated on a shared class, preventing concurrent users from overwriting one another's request credentials.

## Run locally or on your LAN

### Prerequisites

- Docker with a running Docker daemon and Docker Compose v2.
- A TMDB account only if you want online movie lookup. Manual management and existing book providers do not require TMDB.
- Python is not required on the host when using Docker.

### Start

Clone this repository (`main` includes the complete Home Library and Shelfmark feature set):

```bash
git clone https://github.com/kiagithub/Calibre-Web-Automated.git
cd Calibre-Web-Automated
```

Create the local environment file, replace placeholders with credentials only if desired, and build from this source checkout:

```bash
cp .env.example .env
# Edit .env, especially TMDB_READ_ACCESS_TOKEN, then:
docker compose --env-file .env -f compose.home-library.yml up -d --build
```

`.env` and other local environment variants are ignored by git; `.env.example` is the tracked exception and must contain placeholders only. The known TMDB placeholders are treated as **unconfigured**, so copying the example without editing it does not trigger online movie requests.

The Compose paths are relative to the project directory. The build uses this checkout's `Dockerfile` and source; it does **not** pull the upstream `crocodilestick/calibre-web-automated` image.

Open <http://localhost:8083>. CWA's initial credentials are `admin` / `admin123`. **Change the password immediately** in the web UI.

Useful commands, run from the project directory:

```bash
# View application logs
docker compose -f compose.home-library.yml logs -f home-library

# Stop the application; bind-mounted library data remains on disk
docker compose -f compose.home-library.yml down

# Update this branch and rebuild
git pull origin shelfmark
docker compose --env-file .env -f compose.home-library.yml up -d --build
```

For another device on the same network, open `http://YOUR-COMPUTER-LAN-IP:8083`, allowing the port through the host firewall if needed. Do not expose this plain-HTTP port directly to the public internet. For remote access, use a VPN or a properly configured HTTPS reverse proxy.

### Data, backups, and migration

#### Where the files live

| Path | Purpose |
| --- | --- |
| `data/config/app.db` | Users, settings, and the `movie`, `external_book`, and `external_book_tag` tables |
| `data/config/movie_covers/` | Movie posters referenced by `movie.poster_filename` |
| `data/config/movie_backdrops/` | Movie backdrops referenced by `movie.backdrop_filename` |
| `data/config/external_book_covers/` | Personal-book covers referenced by `external_book.cover_filename` |
| `data/config/cwa.db` | CWA settings, including enabled metadata providers |
| `data/config/` | All users, sessions, settings, and authentication data |
| `data/ingest` | CWA book ingest drop folder; processed files are removed |
| `data/calibre-library/` | Calibre files and `metadata.db` |

Inside the container, the config directory is `/config`, the Calibre library is `/calibre-library`, and the ingest folder is `/cwa-book-ingest`.

Movies and personal books share `app.db`; they are not separate databases. Artwork is stored as files beside `app.db`, so the database and all artwork directories must be kept together. Calibre file-backed books live in `data/calibre-library/metadata.db` plus the book files.

The movie and personal-book tables are created by the application at startup; Docker only seeds a base `app.db` on first run. Running CWA outside Docker with `CALIBRE_DBPATH` or `-p /path/to/app.db` creates the same schema.

#### Back up

Stop the container first so SQLite and artwork writes are quiescent:

```bash
docker compose -f compose.home-library.yml down
tar -czf cwa-home-library-$(date +%F).tar.gz data/config data/calibre-library
```

For only movies and personal books:

```bash
docker compose -f compose.home-library.yml down
tar -czf cwa-media-$(date +%F).tar.gz \
  data/config/app.db \
  data/config/movie_covers \
  data/config/movie_backdrops \
  data/config/external_book_covers
```

A backup containing only `app.db` restores the records but leaves covers broken, because each record stores an artwork filename.

The project `.env` file is outside `data/`; copy it separately if you want to preserve TMDB/provider credentials and the `PUID`/`PGID` settings.

#### Restore or move to another system

1. Copy the archive to the new system and extract it.
2. Point the Compose volumes at the restored directories:

   ```yaml
   volumes:
     - /path/to/restored/config:/config
     - /path/to/restored/calibre-library:/calibre-library
   ```

3. Ensure the container user can read and write the files. The default Compose user is `PUID=1000` and `PGID=1000`:

   ```bash
   sudo chown -R 1000:1000 /path/to/restored/config
   ```

4. Start the same or a newer CWA version. Startup creates missing tables and runs the migration pass automatically, including the `movie.created_at` index.

Restore with the same or a newer app version than the one that produced the backup. Migrations are forward-only; restoring a newer `app.db` into an older build is unsupported.

#### Move only movies and personal books

There is no built-in export/import UI yet; import/export remains a separate feature. To copy only the media tables into a fresh `app.db`, leaving the target's users and settings untouched:

1. Start the target app once so it creates the empty tables, then stop it.
2. Copy the tables with SQLite:

   ```bash
   sqlite3 /path/to/target/app.db <<'SQL'
   ATTACH DATABASE '/path/to/source/app.db' AS src;
   BEGIN;
   INSERT INTO movie SELECT * FROM src.movie;
   INSERT INTO external_book SELECT * FROM src.external_book;
   INSERT INTO external_book_tag SELECT * FROM src.external_book_tag;
   COMMIT;
   DETACH DATABASE src;
   SQL
   ```

3. Copy `movie_covers/`, `movie_backdrops/`, and `external_book_covers/` beside the target `app.db`.

The target should be empty, or IDs can collide. `external_book_tag` references `external_book.id`, so books must be inserted before tags. Artwork filenames in the database must match the copied cover directories. Both databases should use the same or a compatible CWA schema version; otherwise migrate the source first and repeat the copy.

#### Live backup

If the container cannot be stopped, SQLite can take a consistent snapshot of the database while running:

```bash
docker compose -f compose.home-library.yml exec home-library \
  sqlite3 /config/app.db ".backup '/config/app-backup-live.db'"
```

Then copy `app-backup-live.db` plus both artwork directories. The snapshot is consistent for the database, but the database and artwork are not captured atomically, so stopping the container is safer for a complete backup.

To use an existing Calibre library, stop other Calibre/CWA processes, make a backup, and replace `./data/calibre-library` in the Compose file with its absolute path. Do not point CWA's ingest folder at the library itself.

### TMDB setup

1. Create an API key or read access token at <https://www.themoviedb.org/settings/api>.
2. Put **one** of these in `.env`:

   ```dotenv
   TMDB_READ_ACCESS_TOKEN=your_token_here
   ```

   or:

   ```dotenv
   TMDB_API_KEY=your_v3_key_here
   ```

3. Restart the container:

   ```bash
   docker compose -f compose.home-library.yml up -d
   ```

The token remains server-side and is never rendered into the page. Metadata requests go only to TMDB's API. Poster downloads are restricted to TMDB's HTTPS image host and have size and image-format checks.

TMDB attribution: **This product uses the TMDB API but is not endorsed or certified by TMDB.**

## Daily use

### Add a personal book

1. Choose **Books**, then **Personal books**, or use **Add Book** on the Books page.
2. Search by title, author, ISBN, or another provider-supported identifier.
3. Select **Use this metadata**, then review the visible fields.
4. Select Physical, Kindle, or Other digital; add personal tags and ownership details.
5. Optionally upload a cover. An uploaded cover takes precedence over a provider cover.
6. Save. The record appears in Personal books, the combined Books catalog, and Home's Books row.

### Add a file-backed Calibre book

Use CWA's existing upload control or move completed files into `/cwa-book-ingest`. The ingest workflow is unchanged and processed files are removed. Personal-book metadata records never enter ingest and do not create Calibre `books` or `data` rows.

### Add a movie

1. Choose **Movies**, then **Add movie**.
2. If TMDB is configured, search by title and optionally release year. Choose the import format and shelf location, then select **Add to library**.
3. Alternatively, complete the manual form and upload a poster.
4. To correct a match later, open the movie, choose **Edit**, and use **Find it on TMDB**. Selecting a result refreshes descriptive metadata without resetting physical-copy details.

### Search URLs

Filters and sorts are ordinary GET parameters, so searches can be bookmarked or shared:

| Surface | Example | Parameters |
| --- | --- | --- |
| Combined books | `/books/?q=dune&source=all` | `q`, `source`, `media_type`, `tag`, `sort`, `direction`, `cursor`, `dir` |
| Personal books | `/books/personal/?q=dune&media_type=physical` | `q`, `media_type`, `tag`, `sort`, `direction`, `page` |
| Movies | `/movies/?q=arrival&format=Blu-ray` | `q`, `format`, `sort`, `direction`, `page` |

Combined books use cursor-based pagination; use the Previous/Next links the page generates rather than constructing `cursor` values by hand. Metadata search also supports targeted `search_by=title|author|isbn|all` field selectors and backend `owned=hide|only` filtering alongside the client-side **Hide owned** toggle.

## Development checks

The project requires Python 3.10 or newer; the current focused suite uses Python 3.13. Provider responses are mocked in unit tests and do not require credentials or live network access. Legacy tests that load stubbed `cps` modules restore `sys.modules` after each module, so `pytest tests/unit` is no longer order-dependent.

```bash
python3.13 -m venv .venv
# Install the project's dependencies, then:
PYTHONPATH=.:scripts .venv/bin/python -m pytest tests/unit
```

Feature-specific coverage lives in:

- `tests/unit/test_movie_library.py` and `test_media.py`
- `tests/unit/test_external_book_models.py`, `test_external_book_forms.py`, `test_external_book_routes.py`, and `test_external_book_ui.py`
- `tests/unit/test_metadata_search.py` covers provider deadline handling and result caching
- `tests/unit/test_external_book_thumbnails.py` covers thumbnail URL policy, resizing fallback, caching, and failures
- `tests/unit/test_catalog_read_models.py`, `test_catalog_service.py`, and `test_catalog_routes.py`
- `tests/unit/test_search_routes.py` covers routing the global search into the combined book catalog
- `tests/unit/test_keyset_pagination.py` covers cursor encoding and the Previous/Next pagination controls
- `tests/unit/test_book_card_accessibility.py`, `test_jinjia_filters.py`, and `test_route_auth.py`
- `tests/unit/test_env_example.py` and `test_hardcover_headers.py`
- `tests/unit/test_favicon.py` covers the SVG brand mark, ICO sizes, PNG dimensions, and template fallback order
- `tests/unit/test_library_check.py`, `test_library_check_providers.py`, and `test_metadata_merge.py` cover ownership matching, provider indexes, and deduplication
- `tests/unit/test_openlibrary_provider.py` covers Open Library parsing and failure handling
- `tests/unit/test_wishlist.py` covers request creation, moderation, limits, and fulfilment
- `tests/unit/test_media_api.py` covers read-only API auth, serialization, filters, stats, and API-key management
- `tests/unit/test_media_preferences.py` and `tests/unit/test_catalog_routes.py` cover per-user catalog view defaults and persistence

Known pre-existing failures in the current environment:

- `tests/unit/test_oauth_session.py` has three stale tests that call removed `*_logged_in` functions.
- `tests/unit/test_ingest_watchers.py::test_ingest_service_shell_script` is environment-specific.

The suite is order-independent and currently reports 508 passed, 18 skipped, 4 failed (the failures above).

A full browser check should exercise Home, Books, Movies, add/edit/delete, metadata selection, filters, collapsed navigation, keyboard focus, and desktop/mobile overflow against an isolated Docker config/library.

## Current status

- The Home Library features above are implemented on `main` (via `shelfmark`) and pushed to `origin`.
- Recent work includes parallel metadata search with a grace window and result caching, lazy cover thumbnails, a shared metadata-search lifecycle, cursor-based Books pagination, combined book search from the navbar, the `movie.created_at` startup index, backup/migration documentation, order-independent legacy tests, the book-and-play favicon, Phase 1 Shelfmark-inspired ownership badges with Open Library, `search_by` field targeting, backend `owned` filtering, and cross-provider deduplication, Phase 2 audiobook catalog support, wishlist/requests, collection stats, and the read-only media API, Phase 3 Hardcover shelf sync with author enrichment, notification preferences, per-user request policies, and companion-library links, Phase 4 optional Audiobookshelf ownership provider and per-user catalog view defaults, and rich movie metadata expansion with TMDB taglines, franchise collections, trailer links, vote counts, and backdrop banner artwork.

## Optional follow-ups

- Run the full browser check described under Development checks against an isolated Docker config/library.
- Exercise keyset Previous/Next against a test library with more than 24 books; cursor behavior and link generation are covered by unit tests, but a multi-page live check remains.
- Repair the pre-existing OAuth and ingest-shell test failures listed under Development checks.
- See `SHELFMARK_PLAN.md` for the proposed Shelfmark-inspired ownership badges, Open Library provider, audiobook catalog support, wishlist/requests, stats, and API work.

## Deliberately deferred clean-cut improvements

These are documented rather than started during the current stabilization pass:

- Consider a shared artwork-replacement transaction object only if another media collection needs it; routes currently own database commits and use the tested shared artwork primitives.
- Per-user watched/read state, private collections, loans, barcode scanning, import/export, additional movie providers, and a movie-inclusive global search remain separate features.
