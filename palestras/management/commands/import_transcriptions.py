import json
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from palestras.models import AudioTrack


class Command(BaseCommand):
    help = "Import transcriptions from a JSON file exported by export_transcriptions"

    def add_arguments(self, parser):
        parser.add_argument(
            "input", help="Input JSON file path"
        )
        parser.add_argument(
            "--overwrite", action="store_true",
            help="Overwrite tracks that are already transcribed",
        )

    def handle(self, *args, **options):
        input_file = options["input"]
        overwrite = options["overwrite"]

        with open(input_file, encoding="utf-8") as f:
            records = json.load(f)

        # Build lookup by id and by mp3_url as fallback
        tracks_by_id = {t.id: t for t in AudioTrack.objects.all()}
        tracks_by_url = {t.mp3_url: t for t in AudioTrack.objects.all()}

        imported = skipped = not_found = 0

        for rec in records:
            track = tracks_by_id.get(rec["id"]) or tracks_by_url.get(rec["mp3_url"])
            if not track:
                self.stdout.write(f"  Not found: {rec['name']} ({rec['palestra_slug']})")
                not_found += 1
                continue

            if track.transcription and not overwrite:
                skipped += 1
                continue

            track.transcription = rec["transcription"]
            track.transcription_timecoded = rec["transcription_timecoded"]
            track.transcription_method = rec["transcription_method"]
            if rec["transcribed_on"]:
                track.transcribed_on = datetime.fromisoformat(rec["transcribed_on"]).replace(tzinfo=timezone.utc)
            track.save()
            imported += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Imported: {imported}, skipped (already transcribed): {skipped}, not found: {not_found}"
        ))
