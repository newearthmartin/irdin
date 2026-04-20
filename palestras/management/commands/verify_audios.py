import logging
import time
from pathlib import Path

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from palestras.models import AudioTrack

logger = logging.getLogger(__name__)

AUDIOS_DIR = Path(settings.MEDIA_ROOT) / "audios"


class Command(BaseCommand):
    help = "Verify downloaded MP3 files by comparing local size with remote Content-Length"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delay", type=float, default=0.3, help="Delay between HEAD requests in seconds"
        )
        parser.add_argument(
            "--limit", type=int, default=0, help="Max tracks to check (0=all)"
        )

    def handle(self, *args, **options):
        delay = options["delay"]
        limit = options["limit"]

        qs = AudioTrack.objects.exclude(local_path=None)
        if limit:
            qs = qs[:limit]

        tracks = list(qs)
        logger.info(f"Checking {len(tracks)} downloaded tracks...\n")

        missing = []
        size_mismatch = []
        head_errors = []
        ok = 0

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            for i, track in enumerate(tracks, 1):
                filename = track.mp3_url.rstrip("/").split("/")[-1]
                local = AUDIOS_DIR / filename

                if not local.exists():
                    logger.error(f"[{i}/{len(tracks)}] MISSING: {filename}")
                    missing.append(track)
                    continue

                local_size = local.stat().st_size

                try:
                    resp = client.head(track.mp3_url)
                    resp.raise_for_status()
                except httpx.HTTPError as e:
                    logger.warning(f"[{i}/{len(tracks)}] HEAD failed: {filename} — {e}")
                    head_errors.append(track)
                    time.sleep(delay)
                    continue

                remote_size = resp.headers.get("content-length")
                if remote_size is None:
                    logger.warning(
                        f"[{i}/{len(tracks)}] No Content-Length: {filename} (local {local_size:,} bytes)"
                    )
                    head_errors.append(track)
                elif int(remote_size) != local_size:
                    logger.error(
                        f"[{i}/{len(tracks)}] SIZE MISMATCH: {filename} "
                        f"(local {local_size:,} vs remote {int(remote_size):,})"
                    )
                    size_mismatch.append(track)
                else:
                    ok += 1
                    if i % 100 == 0 or i == len(tracks):
                        logger.info(f"[{i}/{len(tracks)}] checked, {ok} OK so far")

                time.sleep(delay)

        logger.info("\n--- Summary ---")
        logger.info(f"  OK:             {ok}")
        logger.info(f"  Missing:        {len(missing)}")
        logger.info(f"  Size mismatch:  {len(size_mismatch)}")
        logger.info(f"  HEAD errors:    {len(head_errors)}")

        if missing or size_mismatch:
            logger.warning("\nTo re-download bad files, reset them with:")
            bad_ids = [t.pk for t in missing + size_mismatch]
            logger.info(
                f"  AudioTrack.objects.filter(pk__in={bad_ids}).update(local_path=None)"
            )
            logger.info("  Then run: uv run python manage.py download_audios")
        else:
            logger.info("\nAll files verified!")
