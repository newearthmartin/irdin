import logging

from django.core.management.base import BaseCommand

from palestras.audio_download import download_tracks, pending_tracks

logger = logging.getLogger(__name__)


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

        tracks = pending_tracks()
        if limit:
            tracks = tracks[:limit]
        logger.info(f"Found {len(tracks)} tracks to download")

        total = len(tracks)

        def on_progress(track, filename, saved_bytes, error):
            if error:
                logger.error(f"  Error {filename}: {error}")
            elif saved_bytes:
                logger.info(f"  {filename} ({saved_bytes / (1024*1024):.1f} MB)")

        downloaded, errors = download_tracks(tracks, on_progress=on_progress, delay=delay)

        from palestras.models import AudioTrack
        total_done = AudioTrack.objects.exclude(local_path=None).count()
        total_all = AudioTrack.objects.count()
        logger.info(f"Done. Downloaded: {total_done}/{total_all}")
