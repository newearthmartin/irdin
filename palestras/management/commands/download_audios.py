import time
from pathlib import Path

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from palestras.models import AudioTrack

AUDIOS_DIR = Path(settings.MEDIA_ROOT) / "audios"


class Command(BaseCommand):
    help = "Download MP3 audio files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delay", type=float, default=0.5, help="Delay between downloads in seconds"
        )
        parser.add_argument(
            "--limit", type=int, default=0, help="Max files to download (0=all)"
        )

    def handle(self, *args, **options):
        delay = options["delay"]
        limit = options["limit"]

        AUDIOS_DIR.mkdir(exist_ok=True)

        qs = AudioTrack.objects.filter(downloaded=False)
        if limit:
            qs = qs[:limit]

        pending = list(qs)
        self.stdout.write(f"Found {len(pending)} tracks to download")

        with httpx.Client(timeout=120, follow_redirects=True) as client:
            for i, track in enumerate(pending, 1):
                filename = track.mp3_url.rstrip("/").split("/")[-1]
                dest = AUDIOS_DIR / filename

                if dest.exists():
                    self.stdout.write(f"[{i}/{len(pending)}] Already exists: {filename}")
                    track.local_path = f"audios/{filename}"
                    track.downloaded = True
                    track.save()
                    continue

                self.stdout.write(f"[{i}/{len(pending)}] Downloading: {filename}")

                tmp = dest.with_suffix(".tmp")
                try:
                    with client.stream("GET", track.mp3_url) as resp:
                        resp.raise_for_status()
                        with open(tmp, "wb") as f:
                            for chunk in resp.iter_bytes(chunk_size=65536):
                                f.write(chunk)
                    tmp.rename(dest)
                except httpx.HTTPError as e:
                    self.stderr.write(f"  Error: {e}")
                    if tmp.exists():
                        tmp.unlink()
                    time.sleep(delay)
                    continue

                track.local_path = f"audios/{filename}"
                track.downloaded = True
                track.save()

                size_mb = dest.stat().st_size / (1024 * 1024)
                self.stdout.write(f"  Saved ({size_mb:.1f} MB)")

                time.sleep(delay)

        total_done = AudioTrack.objects.filter(downloaded=True).count()
        total = AudioTrack.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f"Done. Downloaded: {total_done}/{total}")
        )
