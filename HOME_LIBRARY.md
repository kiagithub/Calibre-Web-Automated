# Home Library

Home Library extends [Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated) with a combined book-and-movie collection. File-backed books continue to use Calibre and CWA's existing ingestion, conversion, metadata, Kobo, and OPDS features. Physical movies and books that live outside Calibre use separate tables in CWA's `app.db`; Calibre's `metadata.db` schema is not changed.

## Included

### Home and navigation

- Home has independent **Books** and **Movies** rows with recent items and source-specific detail links.
- **Books** combines Calibre and personal records in a recent-first, paginated catalog.
- **Calibre library** retains the existing Calibre lists, sorting, filters, file actions, shelves, and specialized views.
- **Personal books** provides dedicated management for records without Calibre files.
- **Movies** retains the existing physical-movie shelf.
- The sidebar emphasizes Home, Books, and Movies. Secondary book destinations and shelves remain available in keyboard-native collapsible groups, with existing visibility preferences preserved.
- The global search box is explicitly Calibre-only; it does not claim to search personal books or movies.
- Shared cards use one detail link, consistent 2:3 artwork, responsive grids, visible keyboard focus, and aligned controls.
- Existing Calibre quick actions use native Read, read-status, Edit, and Send buttons outside the cover link. They work with keyboard and touch instead of depending on mouse coordinates or hover alone.
- Legacy `/page/<n>` book links redirect to the existing Calibre newest-book list. Query-string pagination preserves filters and no longer reuses the old page number.

### Personal books

Personal books catalog one owned edition/copy per record. ISBN and provider identifiers are deliberately non-unique, so a physical copy and a Kindle copy—or multiple physical copies—can coexist.

Supported types:

- **Physical**
- **Kindle**
- **Other digital**

Records can contain:
- title, authors, plain-text description, publisher, publication date, series/index, languages, and page count;
- free-form tags with Unicode/case-insensitive normalization and deduplication;
- optional binding, edition, location, condition, acquisition date, collection-wide rating, and notes;
- ISBN-10, ISBN-13, ASIN, metadata provider/ID/source URL, and a local cover.

Manual add/edit/delete and custom JPEG/PNG/WebP cover uploads work without online metadata. Online search reuses CWA's existing enabled book providers, including Google Books and other configured sources. Selecting a result fills the visible form for review before saving; there is no new provider hierarchy or automatic Kindle download/account integration.

Enabled providers run side by side. The search responds shortly after the first sources answer, giving near-simultaneous providers a short grace window, and never waits longer than `CWA_METADATA_SEARCH_TIMEOUT` seconds (default 10). Providers still running after that are left out and the response is marked `X-Metadata-Partial`, so one slow source cannot delay the whole list. Complete result sets are cached in memory for five minutes, scoped to the query, locale, user, and enabled-provider set.

Every result shows a small cover thumbnail beside its details. Thumbnails load lazily through a bounded server-side route, use the same Advocate/local-address policy and image checks as saved covers, are downscaled to thumbnail size, and are cached in memory. Applying metadata still records the provider's full cover URL; the thumbnail is only a preview.

Movie and personal-book metadata search share the fetch, status, error, and focus lifecycle in `cps/static/js/metadata_search.js`; each keeps its own request format and result rendering.

Metadata updates preserve the owned-copy fields, media type, personal tags, location, condition, acquisition details, rating, and notes. Provider tags are suggestions rather than silent replacements.

Records and ratings are shared across library users, matching the movie collection. Viewing follows the normal login/anonymous policy; add/edit and metadata changes require edit permission, deletion requires delete permission, and writes use CSRF protection. Upload permission is not required for a metadata-only record.

### Movies and shared media safety

- TMDB title/year search, metadata import, and refresh retain the existing movie workflows.
- Movie lists sorted by "added" use an indexed `movie.created_at`; startup creates the index idempotently for existing `app.db` files as well as new ones.
- DVD, Blu-ray, 4K UHD, VHS, LaserDisc, Digital, Other, and condition choices are validated server-side.
- Movie and book artwork share bounded image validation, local atomic storage, safe response handling, and upload/download limits.
- New artwork is staged before the database commit; replaced artwork is removed only after a successful commit. Failed saves roll back and discard newly staged files.
- TMDB keeps its HTTPS image-host allowlist. Other provider covers use CWA's Advocate/local-address policy, reject redirects, enforce declared and streamed size limits, close responses, and validate image signatures.
- Metadata-search thumbnails accept only HTTP(S) image URLs on standard ports, require edit permission, reuse the same bounded downloader, fall back to the local generic cover on any failure, and are capped at 256 cached images of at most 256 KiB each.
- Movie poster downloads occur before the import write transaction, avoiding network waits while holding a SQLite write transaction.
- Hardcover authorization headers are copied per request rather than mutated on a shared class, preventing concurrent users from overwriting one another's request credentials.

## Run locally or on your LAN

### Prerequisites

- Docker with a running Docker daemon and Docker Compose v2.
- A TMDB account only if you want online movie lookup. Manual management and existing book providers do not require TMDB.
- Python is not required on the host when using Docker.

### Start

Clone this repository and check out the physical-movies branch:

```bash
git clone https://github.com/kiagithub/Calibre-Web-Automated.git
cd Calibre-Web-Automated
git checkout feature/physical-movies
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
git pull origin feature/physical-movies
docker compose --env-file .env -f compose.home-library.yml up -d --build
```

For another device on the same network, open `http://YOUR-COMPUTER-LAN-IP:8083`, allowing the port through the host firewall if needed. Do not expose this plain-HTTP port directly to the public internet. For remote access, use a VPN or a properly configured HTTPS reverse proxy.

### Data, backups, and migration

#### Where the files live

| Path | Purpose |
| --- | --- |
| `data/config/app.db` | Users, settings, and the `movie`, `external_book`, and `external_book_tag` tables |
| `data/config/movie_covers/` | Movie posters referenced by `movie.poster_filename` |
| `data/config/external_book_covers/` | Personal-book covers referenced by `external_book.cover_filename` |
| `data/config/cwa.db` | CWA settings, including enabled metadata providers |
| `data/config/` | All users, sessions, settings, and authentication data |
| `data/ingest` | CWA book ingest drop folder; processed files are removed |
| `data/calibre-library/` | Calibre files and `metadata.db` |

Inside the container, the config directory is `/config`, the Calibre library is `/calibre-library`, and the ingest folder is `/cwa-book-ingest`.

Movies and personal books share `app.db`; they are not separate databases. Artwork is stored as files beside `app.db`, so the database and both cover directories must be kept together. Calibre file-backed books live in `data/calibre-library/metadata.db` plus the book files.

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

3. Copy `movie_covers/` and `external_book_covers/` beside the target `app.db`.

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
- `tests/unit/test_book_card_accessibility.py`, `test_jinjia_filters.py`, and `test_route_auth.py`
- `tests/unit/test_env_example.py` and `test_hardcover_headers.py`

A full browser check should exercise Home, Books, Movies, add/edit/delete, metadata selection, filters, collapsed navigation, keyboard focus, and desktop/mobile overflow against an isolated Docker config/library.

## Deliberately deferred clean-cut improvements

These are documented rather than started during the current stabilization pass:

- Replace numbered mixed-source pagination with keyset pagination only if a future UI can drop arbitrary page-number jumps. The current recent-first merge preserves numbered pages and exact totals, but later pages read a larger bounded prefix from each source.
- Consolidate remaining legacy/movie/external CSS aliases and duplicate selectors after the shared component behavior is stable.
- Consider a shared artwork-replacement transaction object only if another media collection needs it; routes currently own database commits and use the tested shared artwork primitives.
- Per-user watched/read state, private collections, loans, barcode scanning, import/export, additional movie providers, and unified global search remain separate features.
