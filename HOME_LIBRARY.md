# Home Library

Home Library is a working extension of [Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated), not a replacement for it. Books continue to use Calibre and CWA's existing ingestion, conversion, metadata, Kobo, and OPDS features. Physical movies live in a separate `movie` table in CWA's `app.db`; the Calibre `metadata.db` schema is not changed.

## Included in this first version

- Responsive movie poster grid using CWA's existing theme and navigation.
- Title, cast, director, genre, location, and barcode search.
- Format filters, sorting, and pagination.
- One record per physical copy/edition, allowing multiple formats of the same film.
- DVD, Blu-ray, 4K UHD, VHS, LaserDisc, Digital, and Other formats.
- Shelf/location, barcode, edition, condition, acquisition date, watched state, personal rating, and notes.
- Manual add/edit/delete and custom JPEG/PNG/WebP poster uploads.
- Optional TMDB search, one-click import, and metadata refresh.
- Locally cached posters, persisted in the config volume.
- CWA login and role checks; write operations require edit permission, deletion requires delete permission, and forms use CSRF protection.

Metadata refreshes change the film's descriptive fields only. Format, location, edition, condition, barcode, acquisition date, watched state, personal rating, and notes remain untouched.

## Run locally or on your LAN

### Prerequisites

- Docker with a running Docker daemon and Docker Compose v2.
- A TMDB account if you want online movie lookup. Manual movie management works without it.
- Python is not required on the host when using Docker.

### Start

Clone this repository and check out the physical-movies branch:

```bash
git clone https://github.com/kiagithub/Calibre-Web-Automated.git
cd Calibre-Web-Automated
git checkout feature/physical-movies
```

Create the local environment file, add your TMDB credentials if desired, and build from this source checkout:

```bash
cp .env.example .env
# Edit .env, especially TMDB_READ_ACCESS_TOKEN, then:
docker compose --env-file .env -f compose.home-library.yml up -d --build
```

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

### Data and backups

The Compose file creates these directories next to the project:

| Directory | Purpose |
| --- | --- |
| `data/config` | Users, settings, `app.db`, movie records, and cached movie posters |
| `data/ingest` | CWA book ingest drop folder; processed files are removed |
| `data/calibre-library` | Calibre book library and `metadata.db` |

Back up `data/config` and `data/calibre-library` together while the container is stopped. To use an existing Calibre library, stop other Calibre/CWA processes, make a backup, and replace `./data/calibre-library` in the Compose file with its absolute path. Do not point CWA's ingest folder at the library itself.

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

## Using the movie library

1. Choose **Movies** in the Browse navigation.
2. Choose **Add movie**.
3. If TMDB is configured, search by title and optionally release year. Choose the import format and shelf location, then select **Add to library**. You will land on the edit page to finish physical-copy details.
4. Alternatively, complete the manual form and upload a poster.
5. To correct a match later, open the movie, choose **Edit**, and use **Find it on TMDB**. Selecting a result refreshes the metadata without resetting your physical-copy details.

## Development checks

The project requires Python 3.10 or newer. The focused tests use mocked TMDB responses and do not need an API key or network access:

```bash
python3.13 -m venv .venv
# Install the project's dependencies, then:
PYTHONPATH=.:scripts .venv/bin/python -m pytest tests/unit/test_movie_library.py
```

`tests/unit/test_movie_library.py` covers metadata normalization, authentication credential handling, poster safety, CRUD, search/filter behavior, metadata refreshes, and edit/delete permissions. A full Docker startup/UI check requires the Docker daemon.

## Next useful increments

- Barcode scanner input and UPC-based provider lookup.
- Additional providers such as OMDb, with per-provider priority and credentials.
- Import/export of the movie collection as CSV or JSON.
- Per-user watched state and ratings instead of the current collection-level fields.
- Loan tracking and collections/shelves for movies.
- Optional unified book-and-movie search while keeping each collection's specialized filters.
