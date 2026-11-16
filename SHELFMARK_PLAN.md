# Shelfmark → Home Library: Feature Integration Plan

- **Status:** Draft for review
- **Branch:** `shelfmark`
- **Date:** 2026-11-15
- **Upstream source:** [`calibrain/shelfmark`](https://github.com/calibrain/shelfmark) at revision `9b89857` (2026-11-15)

This document is a plan, not an implementation. It inventories Shelfmark's features, maps them to Home Library's books-and-movies catalog, and proposes a phased roadmap. Nothing here changes the current schema until a phase is approved.

---

## 1. Executive summary

Shelfmark is a **search-and-request hub** for books and audiobooks. It finds titles through metadata providers and release sources, downloads them through torrent, Usenet, IRC, Soulseek, direct-download, or debrid clients, and delivers the files to a library. Home Library is the opposite kind of application: it is an **owned-collection catalog** for Calibre books, personal books, and physical movies.

The valuable overlap is therefore not Shelfmark's download pipeline. It is its catalog-adjacent features:

1. **Already-owned detection** — mark search results that are already in the library.
2. **Metadata provider breadth** — especially Open Library, with optional regional providers.
3. **Audiobook catalog support** — a media type Home Library does not currently model.
4. **Wishlist/request workflow** — users ask for titles an admin can review, approve, and add manually.
5. **Collection stats and a read-only API** — useful for dashboards and integrations.
6. **Shareable search URLs, filters, and external library links** — low-cost usability improvements.

The recommended order is: ownership badges and Open Library first; audiobooks and wishlist/requests next; stats/API and Hardcover shelf sync after that. Download sources, indexers, bypass mechanisms, VPN/Tor routing, and automatic acquisition are explicitly out of scope.

---

## Implementation status — Phase 1 (2026-11-15)

Phase 1 is implemented on the `shelfmark` branch:

- Read-only ownership index for Calibre, personal books, and movies, cached for 10 minutes and refreshed when the underlying data changes.
- **In library** badges in personal-book metadata search and TMDB movie search, naming the source (Calibre, Personal, or Movies).
- **Hide owned** toggle on both metadata-search result lists.
- Open Library metadata provider (no API key).
- Cross-provider deduplication by provider ID, ISBN-10/13, or normalized title + author.
- Documented search URL parameters.
- Unit coverage for matching, provider indexes, deduplication, Open Library parsing, route annotations, and UI contracts.

Remaining Phase 1 follow-ups:

- `owned=hide|only|all` as a URL-persisted catalog filter (the checkbox currently filters client-side only).
- A `search_by=title|author|isbn` selector for metadata search.
- Optional Audiobookshelf ownership provider, which moves with the audiobook work in Phase 2.

## Implementation status — Phase 2 (2026-11-15)

Phase 2 is implemented on the `shelfmark` branch:

- `audiobook` media type with narrator, duration, audio format, and abridged fields; form, detail, filters, and migration.
- Wishlist/request workflow with user creation, admin approval, rejection, reopening, cancellation, and manual fulfilment through the existing Add Book/Add Movie forms.
- Request metadata prefilled from the search results and from the wishlist fulfil action.
- Best-effort email notifications for request creation and decisions.
- Collection stats page and `/api/media/stats`.
- Read-only media API for books, movies, search, and stats.
- Hashed, revocable read-only API keys with a profile-menu management page.
- Unit coverage for wishlist lifecycle, prefill/fulfilment, audiobook fields and migration, stats, API authentication, and API-key management.

Remaining Phase 2 follow-ups:

- Optional Audiobookshelf ownership provider.
- Per-user request policies and overrides (planned for Phase 3).
- URL-persisted `owned` filter and `search_by` selector from Phase 1.

## Implementation status — Phase 3 (2026-11-15)

Phase 3 is implemented on the `shelfmark` branch:

- Optional companion-library links (`AUDIOBOOKSHELF_URL`, `PLEX_URL`, `JELLYFIN_URL`, `GRIMMORY_URL`) in the profile menu.
- Manual Hardcover shelf import on the Wishlist page, skipping owned and already-requested books.
- Scheduled Hardcover shelf import through `HARDCOVER_SYNC_ENABLED`, `HARDCOVER_SYNC_SHELF`, `HARDCOVER_SYNC_CONTENT_TYPE`, and `HARDCOVER_SYNC_INTERVAL_HOURS`.
- Per-user notification opt-out on the Notifications page.
- Admin Request Policies page for per-user open-request limits and allowing/disabling requests.
- Tests for policies, notification preferences, Hardcover sync deduplication, and library-link validation.

Remaining Phase 3/4 follow-ups:

- Optional Audiobookshelf ownership provider.
- Apprise/multi-route notifications.
- URL-persisted `owned` filter and `search_by` selector.
- Custom post-fulfilment hooks, only if a concrete need appears.

---

## 2. Goals and non-goals

### Goals

- Show users when a metadata search result is already owned, so they do not add a duplicate copy.
- Improve discovery with at least one new free metadata provider and cross-provider deduplication.
- Model audiobooks in the personal collection instead of forcing them into "Other digital".
- Give users a wishlist/request path that admins can review and fulfil manually.
- Expose collection stats and a stable read-only JSON API for dashboards and scripts.
- Keep the existing SQLite `app.db` / Calibre `metadata.db` split, backup model, permissions, and server-rendered UI.

### Non-goals

- Torrent, Usenet, IRC, Soulseek, Webshare, Anna's Archive, Prowlarr/Jackett, debrid, or any other download-source integration.
- Cloudflare-bypass, browser automation, Tor, WireGuard, or proxy infrastructure.
- Automatic downloads, automatic release picking, hardlinks, multi-book pack splitting, or post-download rename pipelines.
- Replacing CWA's ingest, conversion, or file-management workflow.
- A new SPA frontend. Home Library stays Jinja + progressive JavaScript.
- A new authentication system. Existing CWA users, OIDC/proxy login, roles, and permissions are reused.
- Audiobook playback work. CWA already has audio metadata extraction and an audio player; this plan only catalogs audiobooks.

---

## 3. Shelfmark feature inventory and fit

| Shelfmark feature | What it does | Fit for Home Library | Decision |
| --- | --- | --- | --- |
| Library Check | Marks search results already owned in Calibre or Audiobookshelf, matching by external ID, ISBN/ASIN, then fuzzy title + author | Excellent fit; extend to personal books and movies | **Adopt in Phase 1** |
| Open Library provider | Free metadata search with covers and ISBNs | Excellent fit; fills a gap in CWA providers | **Adopt in Phase 1** |
| Databáze knih provider | Czech metadata provider | Niche; useful if Czech users need it | **Defer, opt-in** |
| Moly.hu provider | Hungarian metadata provider | Niche; useful if Hungarian users need it | **Defer, opt-in** |
| Hardcover provider | Rich metadata, reading status, lists | CWA already has a Hardcover provider and token support | **Extend only for shelf sync** |
| Audiobook support | Separate content type, audiobook formats, narrator/duration metadata, Audiobookshelf check | Strong fit; personal books have no audiobook type today | **Adapt in Phase 2** |
| Audiobookshelf library check | Read-only REST lookup of owned audiobooks | Optional fit when ABS is present | **Adopt as optional Phase 2** |
| Multi-user requests | Users request books/releases; admins approve, reject, fulfil; notes and history | Strong fit if fulfilment is manual, not a download | **Adapt in Phase 2** |
| Request policies | Per-content-type and per-user download/request/blocked modes | Useful once wishlist exists; simplify to request/approve/blocked | **Adapt in Phase 3** |
| Hardcover shelf sync | Pulls a Hardcover shelf into requests, skips owned books, optional auto-download | Useful as a wishlist import; auto-download is out of scope | **Adapt in Phase 3** |
| Stats | Counts of added items, queue, requests, failures | Adapt to collection growth and wishlist counts | **Adopt in Phase 2** |
| API access | JSON API with an admin key and a read-only key | Useful for dashboards/scripts; CWA has no general media API | **Adopt read-only in Phase 2** |
| URL search parameters | Hash-based search links, filters, search-by targets | Low-cost shareability improvement | **Adopt in Phase 1** |
| Library links | Header links to Calibre-Web/Grimmory/Audiobookshelf/Plex | Useful for companion apps | **Adopt in Phase 3** |
| Per-user settings | Delivery, search, notifications, request policy overrides | Adapt search defaults and request limits; delivery is not applicable | **Adapt in Phase 3** |
| Notifications | Apprise routes for requests/downloads | Email-only first, using CWA's mail path; Apprise later | **Adapt in Phase 3** |
| File processing/renaming | Rename/organize/hardlink downloaded files | CWA ingest already owns this | **Reject** |
| Download sources/indexers | Torrent, Usenet, IRC, Soulseek, direct download, debrid | Out of scope and legally sensitive | **Reject** |
| Bypass/VPN/Tor | Cloudflare solver, Tor, WireGuard | Not needed for a catalog | **Reject** |
| Multi-book packs | Split a release into several books | Download-pipeline concern | **Reject** |
| MyAnonamouse enrichment | Private-tracker metadata | Not applicable | **Reject** |
| Custom post-download scripts | Runs an executable after a download | CWA has its own task/ingest hooks | **Defer** |

---

## 4. Prioritized feature set

### P0 — highest value, lowest risk

1. **Owned badges** in book metadata search and movie TMDB search.
2. **Library ownership index** for Calibre, personal books, and movies.
3. **Open Library** metadata provider.
4. **Cross-provider result deduplication** and consistent owned annotations.
5. **Documented, stable search/filter URL parameters**.

### P1 — next wave

6. **Audiobook media type** and audiobook fields/filters.
7. **Wishlist/request workflow** with manual admin fulfilment.
8. **Collection stats** and a **read-only JSON API**.

### P2 — companion features

9. **Hardcover shelf sync** into the wishlist.
10. **Optional Audiobookshelf library check**.
11. **Email notifications** for request events.
12. **External library links** (Audiobookshelf, Plex/Jellyfin, Grimmory).

### P3 — refinements

13. Regional metadata providers (Databáze knih, Moly.hu) behind explicit opt-in.
14. Per-user catalog defaults and request policies.
15. Apprise notifications.
16. Request history/rejected views and admin reopen actions.
17. Custom post-fulfilment hooks.

---

## 5. Detailed feature specifications

### 5.1 Library ownership index and badges (P0)

**User story:** “When I search for a book or movie to add, show me that I already own it.”

**Behavior**

- A read-only ownership service answers “is this metadata result already in the library?”
- Books are checked against:
  - Calibre `metadata.db` (title, authors, series, identifiers).
  - `external_book` rows in `app.db` (title, authors, ISBN-10/13, ASIN, provider IDs, media type).
  - Optionally an Audiobookshelf server when configured.
- Movies are checked against `movie` rows in `app.db` (TMDB ID, IMDb ID, title + year + director fallback).
- Metadata search results gain:
  - `owned: true|false`
  - `owned_as`: `calibre`, `personal`, `audiobook`, or `movie`
  - a compact “In library” badge.
- A “Hide owned” toggle filters results client-side or server-side.
- The check is **fail-open for badges**: an unreadable library shows no badge, never blocks the search.
- Results are cached for 10 minutes and refreshed when a library file changes.
- A strict mode is available for future automated workflows; it raises instead of guessing.

**Matching order**

1. Exact external identifier: provider + provider ID, ISBN-10/13 variants, ASIN.
2. Exact movie identifier: TMDB or IMDb ID.
3. Fuzzy fallback:
   - Books: significant title tokens + author surname, with guards for sequels, series labels, numbered parentheticals, editions/adaptations, multi-book packs, and “unabridged”/printing words.
   - Movies: normalized title + release year (±1); the Phase 1 TMDB search summary does not include director, so director is only used when a future details-based check supplies it. Reject obvious sequels/remakes when the years disagree.
4. A bundled/omnibus match may be reported as “In library (collection)” rather than a plain “owned” badge.

**Data**

No new owned-media tables. The index is built from existing tables and Calibre's `metadata.db`.
A small cache lives in process memory; no schema change is required for Phase 1.

**Integration points**

- New `cps/media/library_check/` package:
  - `providers/calibre.py` — read-only `metadata.db`, `mode=ro` with `immutable=1` fallback.
  - `providers/personal.py` — `external_book` queries.
  - `providers/movies.py` — `movie` queries.
  - `providers/audiobookshelf.py` — optional REST provider (Phase 2).
  - `matcher.py` — identifier and fuzzy matching.
  - `cache.py` — TTL + fingerprint.
- `cps/search_metadata.py` — annotate metadata results with ownership.
- `cps/movie_library/routes.py` — annotate TMDB search results.
- `cps/templates/external_books/form.html` and `cps/templates/movies/form.html` — badge markup.
- `cps/static/js/external_books.js` and `cps/static/js/movies.js` — render badges and the “Hide owned” toggle.

**Security and failure behavior**

- Calibre is opened read-only; never write to `metadata.db`.
- Fail-open for badges; log a warning once and back off for 60 seconds.
- No network calls for Calibre/personal/movie checks; only the optional ABS provider uses HTTP.

**Tests**

- Identifier matching (ISBN-10 ↔ ISBN-13, ASIN, provider ID).
- Fuzzy matching and its negative cases (sequels, different author, adaptations, omnibuses).
- Movie matching by TMDB/IMDb/title+year.
- Cache refresh by fingerprint and TTL.
- Fail-open behavior and stale-cache fallback.
- Route/UI annotation tests.

**Effort:** Medium.

---

### 5.2 Open Library provider and result deduplication (P0)

**User story:** “I want another good free metadata source, and I do not want the same book five times.”

**Behavior**

- Add an Open Library provider using its public search API:
  - Search: `https://openlibrary.org/search.json?q=…`
  - Covers: Open Library cover IDs (`https://covers.openlibrary.org/b/id/{cover_i}-M.jpg`).
  - Extract title, authors, ISBN-10/13, publisher, publish year/date, languages, subjects/tags, series where available.
- No API key required; respect rate limits and set a bounded timeout.
- Deduplicate metadata results across all providers:
  - First by exact ISBN-10/13 or provider identifier.
  - Then by normalized title + author.
  - Keep the best-scoring record and preserve alternate provider links/editions.
- Add “Hide owned” and “Only owned” filters once ownership annotations exist.
- Phase 1 keeps the existing `Metadata.search(query, generic_cover, locale)` interface; provider capabilities (search-by title/author/ISBN, sort) can be a later interface extension.

**Data**

No schema change. Provider results are `MetaRecord` objects as today.

**Integration points**

- New `cps/metadata_provider/openlibrary.py`.
- `cps/search_metadata.py` — deduplication and ownership annotation after provider results merge.
- Settings UI already lists providers; Open Library appears automatically once the module is discovered.

**Tests**

- Parsing fixtures for search results, covers, ISBNs, languages, and series.
- Deduplication by ISBN and by title + author.
- No-network test for unconfigured/mocked provider behavior.

**Effort:** Medium.

---

### 5.3 Audiobook catalog support (P1)

**User story:** “I own audiobooks too; I want them in my personal collection and filterable.”

**Behavior**

- Add `audiobook` to `MEDIA_TYPES` alongside `physical`, `kindle`, and `other_digital`.
- Add audiobook-specific fields to `external_book`:
  - `narrator` (string)
  - `duration_minutes` (integer)
  - `abridged` (boolean)
  - `audio_format` (`M4B`, `MP3`, `Other`)
  - optionally `is_listened` or listening progress later
- Add form controls, detail rows, filters, sort options, and labels.
- Metadata search:
  - Prefer providers that expose audiobook editions (Open Library/Hardcover when available; optional Audiobookshelf search later).
  - Capture ASIN, narrator, duration, and abridged status when the provider supplies them.
- Library check treats audiobooks as their own content type and checks `external_book` rows with `media_type = 'audiobook'`.
- Optional Audiobookshelf provider:
  - Configure URL, token, and optional library IDs.
  - Read-only `/api/libraries/{id}/items`.
  - Match by ASIN/ISBN first, then title + author.
- CWA already handles audio file metadata and playback; this feature does not change file handling.

**Data**

- Add columns to `external_book` via an explicit migration:
  - `narrator VARCHAR(300) NOT NULL DEFAULT ''`
  - `duration_minutes INTEGER`
  - `abridged BOOLEAN NOT NULL DEFAULT 0`
  - `audio_format VARCHAR(20) NOT NULL DEFAULT ''`
- Add `audiobook` to `MEDIA_TYPES` and update `MEDIA_TYPE_LABELS`.
- No change to `movie`.

**Integration points**

- `cps/external_books/models.py`, `forms.py`, `routes.py`, `query.py`.
- `cps/catalog/read_models.py` labels and card badges.
- `cps/templates/external_books/form.html`, `detail.html`, `index.html`.
- `cps/static/css/media.css`.
- Migrations in `cps/ub.py` and tests for existing databases.

**Tests**

- Form parsing and validation of the new fields.
- Migration on a database that predates the columns.
- Filters/sorts and card badges.
- Optional ABS provider with mocked API responses.
- Audiobook ownership matching.

**Effort:** Medium–Large.

---

### 5.4 Wishlist and request workflow (P1)

**User story:** “I want a book or movie that is not in the library yet; I can ask an admin to add it.”

**Behavior**

- Users create a request from:
  - a metadata search result (book/audiobook),
  - a TMDB search result (movie),
  - a manual title/identifier entry.
- Request fields: title, authors/director, identifiers, provider/source URL, cover URL, note, content type.
- Status lifecycle:
  - `pending` → `approved` → `fulfilled`
  - `pending` → `rejected`
  - `pending` → `cancelled` by the requester
  - `rejected` → `pending` when reopened by an admin
- Admin actions:
  - Approve, reject with note, reopen, fulfil.
  - Fulfil prefills the existing Add Book/Add Movie form with the request metadata and, on save, links the new owned record back to the request.
- User actions:
  - Create, view own requests, cancel pending requests, add notes.
- Policies:
  - Default mode per content type: `request` or `blocked`.
  - Optional `max_pending_requests_per_user`.
  - Optional “allow notes”.
  - Per-user overrides can come later.
- Notifications:
  - Email the admins when a request is created.
  - Email the requester when it is approved, rejected, or fulfilled.
  - Respect existing CWA mail configuration; no new mandatory dependency.
- No automatic acquisition or download.

**Data**

New table `media_request`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | Integer PK | |
| `user_id` | Integer FK → `user.id` | requester |
| `content_type` | String(20) | `book`, `audiobook`, `movie` |
| `status` | String(20) | `pending`, `approved`, `rejected`, `fulfilled`, `cancelled` |
| `title` | String(300) | |
| `authors_json` | Text | books/audiobooks |
| `director` | String(300) | movies |
| `identifiers_json` | Text | ISBN/ASIN/TMDB/IMDb |
| `metadata_provider` | String(50) | |
| `metadata_id` | String(255) | |
| `metadata_url` | String(1000) | |
| `cover_url` | String(2000) | |
| `note` | Text | requester note |
| `admin_note` | Text | decision note |
| `decided_by` | Integer FK → `user.id` | |
| `decided_at` | DateTime | |
| `fulfilled_external_book_id` | Integer FK | nullable |
| `fulfilled_movie_id` | Integer FK | nullable |
| `created_at` | DateTime | indexed |
| `updated_at` | DateTime | |

Indexes: `status`, `user_id`, `content_type`, `created_at`.

Settings live in the existing CWA settings store (or `app.db` settings), not new tables:
`requests_enabled`, `request_default_book_mode`, `request_default_movie_mode`,
`request_max_pending_per_user`, `request_allow_notes`.

**Integration points**

- New `cps/requests/` package: `models.py`, `routes.py`, `service.py`, `forms.py`.
- New blueprint registered in `cps/main.py`.
- Templates: `cps/templates/requests/index.html`, `detail.html`, `new.html`.
- Nav entry in `layout.html`; badges for pending admin count.
- Add Book/Add Movie forms accept prefill query params or a request token.
- `cps/tasks/mail.py` or a small notification service for email.
- Permissions: authenticated users create; editors/admins approve/fulfil; requesters cancel their own.

**Tests**

- Status transitions and permissions.
- Max-pending policy.
- Fulfilment links the created media record and marks the request fulfilled.
- CSRF and auth on HTML routes.
- Notification calls mocked.
- Migration/create-table tests.

**Effort:** Large.

---

### 5.5 Hardcover shelf sync into wishlist (P2)

**User story:** “Import my Hardcover ‘Want to Read’ shelf into the wishlist automatically.”

**Behavior**

- Use the existing CWA Hardcover token (`ub.User.hardcover_token`) or a global token.
- Fetch a configured reading shelf (default: Want to Read).
- Create pending `media_request` rows for books not already requested/owned.
- Skip when the library check says the book is owned.
- Deduplicate by Hardcover book ID, then title + author + content type.
- Optionally run on a schedule (daily/weekly) using CWA's background scheduler.
- **No automatic download or acquisition.** The result is a curated wishlist/admin queue.
- Fail closed for a sync cycle if an enabled library check cannot be read, so owned books are not re-requested.

**Data**

No new table; writes `media_request` rows. Settings:
`hardcover_sync_enabled`, `hardcover_sync_shelf`, `hardcover_sync_content_type`,
`hardcover_sync_interval_hours`.

**Integration points**

- `cps/metadata_provider/hardcover.py` and existing Hardcover token plumbing.
- `cps/services/background_scheduler.py`.
- `cps/requests/service.py` for idempotent request creation.
- New settings in `cwa_settings.html` / `cwa_functions.py`.

**Tests**

- Mocked Hardcover shelf responses.
- Owned-book skip and duplicate suppression.
- Scheduler registration and interval bounds.
- Failure behavior when the library check is unavailable.

**Effort:** Medium.

---

### 5.6 Collection stats and read-only API (P1)

**User story:** “I want a dashboard and a scriptable view of my collection.”

**Stats**

- Add a Home Library section to the existing CWA stats page or a dedicated stats route:
  - total books and movies;
  - counts by media type/format;
  - added in the last 7/30 days;
  - wishlist/request counts by status;
  - top tags, locations, ratings, and languages;
  - optional ownership-check cache status.
- No titles or user names in the public/read-only API stats response.

**API**

- Read-only endpoints first:
  - `GET /api/media/books`
  - `GET /api/media/movies`
  - `GET /api/media/books/<id>`
  - `GET /api/media/movies/<id>`
  - `GET /api/media/stats`
  - `GET /api/media/search?q=…`
- Auth:
  - Per-user API key table (`api_key`) or a configured admin key; prefer hashed per-user keys.
  - `Authorization: Bearer …` and `X-Api-Key`.
  - Read-only keys restricted to stats/read endpoints.
  - Constant-time comparison; never log keys.
- Pagination:
  - Reuse the existing keyset pagination for books; offset/page for movies initially.
- Content:
  - JSON serializers for `ExternalBook`, `Movie`, and catalog cards.
  - No file paths, user tokens, or other private values.
- Writes (add/edit/delete/request) can follow later behind edit permission.

**Data**

- New `api_key` table: `id`, `user_id`, `name`, `key_hash`, `readonly`, `created_at`,
  `last_used_at`, `revoked_at`.

**Integration points**

- New `cps/media_api.py` blueprint.
- `cps/catalog/service.py` and `cps/requests/service.py` for data access.
- `cps/templates/user_edit.html` or a new account section for key management.
- `cps/cwa_functions.py` stats route additions if using the existing stats page.

**Tests**

- API auth (valid, invalid, revoked, read-only).
- Serializer shape and permission filtering.
- Pagination and filters.
- Stats counts.
- No sensitive fields in responses.

**Effort:** Medium.

---

### 5.7 URL search parameters, filters, and library links (P0/P2)

**URL parameters**

Document and stabilize:

| Surface | Parameters |
| --- | --- |
| Combined books | `q`, `source`, `media_type`, `tag`, `sort`, `direction`, `cursor`, `dir` |
| Personal books | `q`, `media_type`, `tag`, `sort`, `direction` |
| Movies | `q`, `format`, `sort`, `direction`, `page` |
| Future | `content_type`, `search_by`, `owned` |

- Keep filters in pagination and sort links.
- Add `owned=hide|only|all` once ownership badges exist.
- Add `search_by=title|author|isbn` to the metadata search form when provider capabilities allow it.
- Document examples in `HOME_LIBRARY.md`.

**Library links**

- Admin setting for companion library URLs:
  - Audiobookshelf
  - Plex or Jellyfin (movies)
  - Grimmory (books)
  - Calibre-Web (another instance)
- Render them in the header/sidebar only when configured.
- Validate URLs; reject `javascript:` and malformed values.

**Effort:** Small.

---

### 5.8 Notifications (P2)

- Reuse CWA's existing SMTP/mail configuration.
- Events:
  - request created (admins),
  - request approved/rejected (requester),
  - request fulfilled (requester),
  - Hardcover sync summary (admins),
  - optionally new media added.
- Per-user opt-out or per-event preference can be stored in `user.view_settings`.
- Apprise-style multi-route notifications are a later optional extension; do not add the dependency in Phase 1.

**Effort:** Medium.

---

### 5.9 Per-user settings and request policies (P3)

- Per-user search defaults: source, media type, tag, sort, and “hide owned”.
- Per-user request policy overrides: request/blocked, max pending.
- Per-user notification preferences.
- Store in `ub.User.view_settings` JSON to avoid new columns.
- Admin UI under user management; self-service under My Account.
- Capability is deliberately later because it touches permissions and UI in several places.

**Effort:** Medium–Large.

---

## 6. Data model and migration plan

### New tables

- `media_request` (Section 5.4).
- `api_key` (Section 5.6).

Both are created by `Base.metadata.create_all()` for new databases. Existing `app.db` files also need an explicit migration path because `create_all()` only creates missing tables, which is fine for new tables; columns added to existing tables need `ALTER TABLE` in `cps/ub.py:migrate_Database`.

### Modified tables

- `external_book`:
  - allow `audiobook` in `media_type`;
  - add `narrator`, `duration_minutes`, `abridged`, `audio_format`.
- No `movie` schema change is required for Phase 1–3. Movie requests live in `media_request`.

### Migration rules

- Add idempotent `ALTER TABLE` checks for every new column.
- Add indexes for `media_request(status)`, `media_request(user_id)`, `media_request(created_at)`, and `api_key(key_hash)`.
- Keep Calibre's `metadata.db` untouched.
- Back up and restore documentation already covers `app.db` and artwork; extend it with the new tables if needed.
- Test migrations against a copy of a pre-change `app.db`.

---

## 7. Architecture and integration points

| Area | Existing files | Planned additions |
| --- | --- | --- |
| Ownership check | `cps/search_metadata.py`, `cps/movie_library/routes.py` | `cps/media/library_check/` package |
| Metadata providers | `cps/metadata_provider/*.py` | `openlibrary.py`, later `databazeknih.py`, `moly.py` |
| Personal books | `cps/external_books/*` | audiobook fields, forms, filters, badges |
| Movies | `cps/movie_library/*` | owned badges, request entry points |
| Catalog | `cps/catalog/*` | owned filter, `content_type`, API serializers |
| Requests | new package | `cps/requests/*`, blueprint, templates, nav |
| Stats | `cps/cwa_functions.py` | media stats cards/API |
| API | new blueprint | `cps/media_api.py`, API key model/routes |
| Scheduler | `cps/services/background_scheduler.py` | Hardcover sync job |
| Settings | `cps/cwa_functions.py`, `cps/templates/cwa_settings.html`, `scripts/cwa_db.py` | new settings keys and sections |
| UI | `cps/templates/*`, `cps/static/css/media.css`, `cps/static/js/*` | badges, wishlist, audiobook fields, links |
| Tests | `tests/unit/*` | matcher, cache, provider, request, API, migration tests |

---

## 8. Phased roadmap

### Phase 0 — Plan and decisions (this document)

- Approve scope and non-goals.
- Decide whether movies are included in wishlist from day one.
- Decide whether audiobook playback is in scope (recommended: no).
- Decide API-key model (per-user vs single admin key).
- Confirm naming: `Shelfmark` is used only as an inspiration/reference; new code uses Home Library names.

### Phase 1 — Ownership and discovery (P0)

Deliverables:

- Library check service + Calibre/personal/movie providers.
- Owned badges in book metadata search and movie TMDB search.
- “Hide owned” toggle.
- Open Library provider.
- Cross-provider deduplication.
- URL parameter documentation.
- Tests and `HOME_LIBRARY.md` updates.

Exit criteria:

- Existing library, personal-book, and movie routes pass.
- A personal book found by metadata search shows “In library” when already saved.
- A movie found by TMDB search shows “In library” when already added.
- Open Library results appear without an API key.
- No duplicate cards for the same ISBN/provider ID.

### Phase 2 — Audiobooks and wishlist (P1)

Deliverables:

- `audiobook` media type and fields, forms, filters, detail display.
- Optional Audiobookshelf ownership provider.
- `media_request` table, request routes, admin queue, fulfilment flow.
- Email notifications for request events.
- Collection stats page/API counts.
- Read-only media API and API-key management.
- Tests and docs.

Exit criteria:

- Audiobooks can be added, edited, filtered, and checked as owned.
- A user can request a book/movie; an admin can reject or fulfil it; fulfilment creates the owned record and links back.
- Read-only API returns books, movies, and stats with a valid key and 401/403 otherwise.
- Existing backup/migration documentation covers new tables.

### Phase 3 — Companion features (P2)

Deliverables:

- Hardcover shelf sync into wishlist, scheduled.
- External library links.
- Notification preferences.
- Optional request policy overrides.
- More complete stats and request history/rejected views.

### Phase 4 — Refinements (P3)

Deliverables:

- Databáze knih / Moly.hu providers behind settings.
- Apprise notifications.
- Per-user search defaults.
- Custom post-fulfilment hooks (if a concrete need appears).

---

## 9. Testing strategy

### Unit

- Library matcher: identifiers, ISBN variants, ASIN, title/author fuzzy rules, series/sequel/edition/adaptation/omnibus guards.
- Movie matcher: TMDB/IMDb exact, title/year/director fuzzy, remakes.
- Cache: TTL, fingerprint refresh, failure backoff, stale fallback.
- Metadata providers: Open Library parsing fixtures, missing fields, rate-limit/timeout errors.
- Deduplication: ISBN, provider ID, title + author.
- Audiobook forms and migration.
- Request lifecycle: create, cancel, approve, reject, reopen, fulfil; permissions; max pending.
- API: key auth, read-only restrictions, pagination, serializers, sensitive-field exclusion.
- Stats: counts, time windows.
- Hardcover sync: mocked shelf, owned skip, dedupe, scheduling.

### Integration / UI

- Route tests for badges, filters, wishlist, settings, and API.
- Static tests for templates and JS (existing style).
- Browser checks: metadata search badge, hide-owned, audiobook form, request flow, admin queue, mobile layout.

### Performance

- Index a 10,000-book Calibre library and assert cache/index time is bounded.
- Ensure metadata search with ownership checks does not serially scan the library per result.
- Keep the existing metadata search grace window and caching.

### Regression

- Keep the current `tests/unit` suite green (currently 444 passed, 18 skipped, 4 known pre-existing failures).
- Fix the stale OAuth and ingest-shell failures before or during Phase 1 if they interfere with CI.

---

## 10. Security, privacy, and licensing

- **Read-only library access:** Calibre `metadata.db` is opened read-only, never written.
- **SSRF:** Audiobookshelf/Plex/Jellyfin URLs are validated; disallow non-HTTP(S) schemes and unexpected local addresses unless the admin explicitly allows localhost.
- **API keys:** hash keys at rest, compare in constant time, support revocation, never log them, and separate read-only keys from write keys.
- **Permissions:** request creation is authenticated; approval/fulfilment requires edit/admin; API writes require edit permission.
- **CSRF:** HTML forms keep CSRF protection; API uses bearer keys and is CSRF-exempt.
- **Notifications:** do not include private notes or user emails in logs; respect user opt-outs.
- **Data minimization:** stats/read-only API omit titles, user names, file paths, and provider tokens.
- **Licensing:** Shelfmark is MIT-licensed; this project is GPL-3.0-or-later. Ideas and behavior can be reimplemented independently. If any Shelfmark code is copied, retain its copyright/license notice and add a `THIRD_PARTY_NOTICES` entry. The default is a clean-room reimplementation guided by the docs.

---

## 11. Risks and open questions

1. **Scope creep into a download manager.** The biggest risk. Keep acquisition manual and clearly label Wishlist as a request queue, not an auto-downloader.
2. **Matching false positives/negatives.** Tune with a fixture corpus; prefer “unknown” over a wrong “owned” badge.
3. **Audiobook semantics.** Do we store narrator/duration only, or also listening progress and playback links? Recommended: catalog fields first, progress later.
4. **Request ownership.** Should requests belong to a user or be shared? Recommended: user-owned with admin visibility, matching Shelfmark's model.
5. **Movie requests.** Include movies from day one? Recommended: yes for a consistent wishlist; content_type distinguishes them.
6. **Hardcover API.** Token scopes and rate limits; reuse CWA's existing token and provider where possible.
7. **External library checks.** Audiobookshelf/Plex/Jellyfin require credentials and network reachability; keep them optional and fail-open for badges.
8. **Regional provider terms.** Databáze knih and Moly.hu may have scraping/rate limits; keep them opt-in and documented.
9. **API key management.** Per-user keys are more work than a single admin key but safer; decide before Phase 2.
10. **UI density.** Badges, filters, wishlist, and audiobook fields add complexity; use progressive disclosure and keep the existing media card system.
11. **Migration safety.** New columns require idempotent migrations and backup tests; never touch Calibre's schema.
12. **Notification noise.** Default to admin request-created and requester decision emails; make optional events opt-in.

---

## 12. Explicit non-goals (repeated for emphasis)

- No torrent, Usenet, IRC, Soulseek, Webshare, Anna's Archive, Prowlarr/Jackett, debrid, or direct-download sources.
- No automated downloads or release matching.
- No Cloudflare bypass, Tor, WireGuard, or proxy infrastructure.
- No file renaming, hardlinking, archive extraction, or multi-book pack splitting.
- No audiobook acquisition or playback changes.
- No replacement of CWA ingest/conversion.
- No public multi-tenant request instance; requests are for the existing authenticated users.

---

## 13. Appendix A — Shelfmark references

Primary sources inspected:

- `readme.md` — product scope and feature list.
- `docs/library-check.md` — ownership matching, caching, fail-open/fail-closed behavior.
- `docs/users-and-requests.md` — request lifecycle, policies, per-user settings.
- `docs/hardcover-sync.md` — shelf sync, dedupe, book matching.
- `docs/url-search-parameters.md` — shareable search links and filters.
- `docs/api-access.md` — API keys, read-only keys, security notes.
- `docs/custom-scripts.md` — post-processing hooks (not adopted).
- `shelfmark/core/library_providers/` — provider interface and Calibre/Audiobookshelf implementations.
- `shelfmark/core/library_index.py` and `existence_match.py` — matching and caching.
- `shelfmark/core/request_policy.py` and `requests_service.py` — request modes and lifecycle.
- `shelfmark/metadata_providers/` — provider interface and Open Library/Databáze knih/Moly.hu implementations.
- `shelfmark/core/models.py` — download/request/queue data structures.
- `shelfmark/core/stats.py` and `notifications.py` — stats and notification patterns.

---

## 14. Appendix B — Matching rules adapted from Shelfmark

For books and audiobooks:

1. Exact provider ID (`provider` + `provider_id`).
2. ISBN-10/ISBN-13 in either normalized form.
3. ASIN for audiobook editions.
4. Fuzzy: significant title tokens + author surname.
5. Guards:
   - Strip series labels and numbered parentheticals from the comparison title.
   - Reject sequels and different works in the same series.
   - Reject summaries, study guides, workbooks, abridged/dramatized/adapted editions, and graphic-novel adaptations unless the requested title itself carries the word.
   - Treat “unabridged” and printing words as non-disqualifying.
   - Reject multi-book packs and omnibuses for a single-work match, but report “collection” when appropriate.
   - Match audiobooks only against audiobook libraries when content type is known.

For movies:

1. Exact TMDB ID.
2. Exact IMDb ID.
3. Normalized title + release year (±1), plus director when the source provides it. Phase 1's TMDB search summaries expose TMDB ID and title/year but not director.
4. Reject remakes/sequels when the years disagree.
5. A movie in a collection/box set may be reported as “In library (collection)”.

---

## 15. Appendix C — API sketch

```text
GET /api/media/books?q=&source=&media_type=&tag=&sort=&direction=&cursor=&dir=
GET /api/media/books/<id>
GET /api/media/movies?q=&format=&sort=&direction=&page=
GET /api/media/movies/<id>
GET /api/media/search?q=&content_type=book|audiobook
GET /api/media/stats
GET /api/media/requests?status=&content_type=
POST /api/media/requests
POST /api/media/requests/<id>/approve
POST /api/media/requests/<id>/reject
POST /api/media/requests/<id>/fulfil
```

Auth:

```http
Authorization: Bearer <api-key>
X-Api-Key: <api-key>
```

Responses omit file paths, provider tokens, user emails, and admin notes unless the caller is an admin.

---

## 16. Appendix D — Settings keys (proposed)

| Key | Purpose | Default |
| --- | --- | --- |
| `library_check_calibre_enabled` | Check Calibre ownership | off |
| `library_check_calibre_db_path` | `metadata.db` path | `/calibre-library/metadata.db` |
| `library_check_audiobookshelf_enabled` | Check ABS ownership | off |
| `audiobookshelf_url` | ABS base URL | empty |
| `audiobookshelf_token` | ABS API token | empty |
| `audiobookshelf_library_ids` | Comma-separated ABS library IDs | empty |
| `requests_enabled` | Enable wishlist/requests | off |
| `request_default_book_mode` | `request` or `blocked` | `request` |
| `request_default_movie_mode` | `request` or `blocked` | `request` |
| `request_max_pending_per_user` | Open request limit | 20 |
| `request_allow_notes` | Allow request notes | on |
| `hardcover_sync_enabled` | Sync a Hardcover shelf into wishlist | off |
| `hardcover_sync_shelf` | Hardcover shelf/status | Want to Read |
| `hardcover_sync_interval_hours` | Sync interval | 24 |
| `api_key_readonly` | Optional read-only dashboard key | empty |

All settings are optional, default-off where they enable outbound network calls, and editable from the CWA settings UI.

Phase 1 implements the local Calibre/personal/movie checks as always-on, read-only, cached lookups; the `library_check_*_enabled` toggles are proposed for a later phase, when optional external providers (Audiobookshelf/Plex) are added.

---

## 17. Recommendation

Start with **Phase 1** only. It delivers the highest user value with no new third-party dependency and no new acquisition workflow:

- ownership index and badges for books and movies,
- Open Library,
- deduplication,
- documented shareable search URLs.

That work also creates the matching/caching primitives the audiobook and wishlist phases need. Phase 2 should begin only after Phase 1's matching quality and performance are validated against a real Calibre library.
