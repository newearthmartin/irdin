import json

from django.core.management.base import BaseCommand

from palestras.models import AudioTrack


class Command(BaseCommand):
    help = "Export transcriptions to a JSON file"

    def add_arguments(self, parser):
        parser.add_argument(
            "output", nargs="?", default="transcriptions_export.json",
            help="Output file path (default: transcriptions_export.json)",
        )

    def handle(self, *args, **options):
        output = options["output"]
        qs = AudioTrack.objects.exclude(transcription="").select_related("palestra")
        records = []
        for t in qs:
            records.append({
                "id": t.id,
                "mp3_url": t.mp3_url,
                "name": t.name,
                "palestra_slug": t.palestra.slug,
                "transcription": t.transcription,
                "transcription_timecoded": t.transcription_timecoded,
                "transcription_method": t.transcription_method,
                "transcribed_on": t.transcribed_on.isoformat() if t.transcribed_on else None,
            })

        with open(output, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        self.stdout.write(self.style.SUCCESS(f"Exported {len(records)} transcriptions to {output}"))
