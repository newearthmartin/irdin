# IRDIN Scraper

Scraper for https://www.irdin.org.br/ lecture audio files and metadata.

## Project Structure

- **Django project**: `irdin/` (settings, urls, views)
- **Django app**: `palestras/` (models, views, management commands)
- **Frontend**: `frontend/` (React 19 + Vite, builds to `static/frontend/`)
- **Audio files**: `audios/` (gitignored, downloaded MP3s)
- **Transcriptions**: `transcriptions/` (plain and timecoded text files)

## Commands

```bash
# Run with uv
uv run python manage.py scrape_urls        # Phase A: collect product URLs (~1983)
uv run python manage.py scrape_products     # Phase B: scrape metadata from each product page
uv run python manage.py download_audios     # Phase C: download MP3 files
uv run python manage.py verify_audios       # Check MP3 integrity via HEAD requests
uv run python manage.py transcribe          # Transcribe audio tracks
uv run python manage.py extract_concepts    # Extract concepts from transcriptions via Ollama

# Common options
--delay 1.0       # seconds between requests (scrape commands)
--limit 10        # max items to process (scrape_products, download_audios, transcribe, extract_concepts)
--start-page 5    # resume from page N (scrape_urls)
--workers 4       # parallel workers (scrape_products)

# Transcribe options
--backend faster-whisper|mlx-whisper|groq|whisper-cpp  # default: faster-whisper
--model <name>    # override default model for chosen backend
--retranscribe    # re-transcribe tracks done with a different method
```

## API Endpoints

- `/api/search` — full-text search with pagination and field filtering
- `/api/palestras/<slug>` — palestra detail with tracks and metadata
- `/media/<path>` — media file serving with Range request support

## Models

- `Author`: name, slug
- `Palestra`: title, slug, url, description, sku, categories, tags, weight, dimensions, media_format, authors (M2M), scraped_on (DateTimeField)
- `AudioTrack`: palestra (FK), name, mp3_url, local_path, downloaded (bool), transcription, transcription_timecoded, transcription_method, transcribed_on, concepts (JSONField)

## Conventions

- Python managed with `uv` (no pip, no venv activation needed)
- All commands are resumable — they skip already-processed records
- SQLite database at `db.sqlite3`
- Keep this CLAUDE.md updated when adding new commands, models, or conventions
- Do not include "Co-Authored-By" or any Claude references in git commit messages
