# IRDIN Scraper

Scraper for https://www.irdin.org.br/ lecture audio files and metadata.

## Project Structure

- **Django project**: `irdin/` (settings, urls)
- **Django app**: `palestras/` (models, management commands)
- **Audio files**: `audios/` (gitignored, downloaded MP3s)

## Commands

```bash
# Run with uv
uv run python manage.py scrape_urls        # Phase A: collect product URLs (~1983)
uv run python manage.py scrape_products     # Phase B: scrape metadata from each product page
uv run python manage.py download_audios     # Phase C: download MP3 files

# Options
--delay 1.0       # seconds between requests (all commands)
--limit 10        # max items to process (scrape_products, download_audios)
--start-page 5    # resume from page N (scrape_urls)
```

## Models

- `Author`: name, slug
- `Palestra`: title, slug, url, description, sku, categories, tags, weight, dimensions, media_format, authors (M2M), scraped (bool)
- `AudioTrack`: palestra (FK), name, mp3_url, local_path, downloaded (bool)

## Conventions

- Python managed with `uv` (no pip, no venv activation needed)
- All commands are resumable — they skip already-processed records
- SQLite database at `db.sqlite3`
