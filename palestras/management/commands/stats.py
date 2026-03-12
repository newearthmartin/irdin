from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from palestras.models import AudioTrack, Author, Palestra


class Command(BaseCommand):
    help = "Show database and content statistics"

    def handle(self, *args, **options):
        # Palestras
        total_palestras = Palestra.objects.count()
        scraped = Palestra.objects.filter(scraped_on__isnull=False).count()
        with_description = Palestra.objects.exclude(description="").count()
        no_tracks = Palestra.objects.filter(tracks__isnull=True).count()

        # Authors
        total_authors = Author.objects.count()
        with_photo = Author.objects.exclude(photo="").count()

        # Tracks
        total_tracks = AudioTrack.objects.count()
        downloaded = AudioTrack.objects.exclude(local_path="").exclude(local_path__isnull=True).count()
        not_downloaded = total_tracks - downloaded

        transcribed = AudioTrack.objects.exclude(transcription="").count()
        timecoded = AudioTrack.objects.exclude(transcription_timecoded="").count()
        not_transcribed = total_tracks - transcribed
        with_concepts = AudioTrack.objects.filter(concepts__len__gt=0).count()

        methods = (
            AudioTrack.objects.exclude(transcription_method="")
            .values("transcription_method")
            .annotate(n=Count("id"))
            .order_by("-n")
        )

        w = self.style.WARNING
        s = self.style.SUCCESS
        e = self.style.ERROR

        self.stdout.write("")
        self.stdout.write(w("=== Palestras ==="))
        self.stdout.write(f"  Total:               {total_palestras}")
        self.stdout.write(f"  Scraped:             {s(str(scraped))}  ({total_palestras - scraped} pending)")
        self.stdout.write(f"  With description:    {with_description}")
        self.stdout.write(f"  Without tracks:      {e(str(no_tracks)) if no_tracks else s('0')}")

        self.stdout.write("")
        self.stdout.write(w("=== Authors ==="))
        self.stdout.write(f"  Total:               {total_authors}")
        self.stdout.write(f"  With photo:          {with_photo}  ({total_authors - with_photo} without)")

        self.stdout.write("")
        self.stdout.write(w("=== Audio Tracks ==="))
        self.stdout.write(f"  Total:               {total_tracks}")
        self.stdout.write(f"  Downloaded:          {s(str(downloaded))}  ({e(str(not_downloaded)) if not_downloaded else s('0')} missing)")
        self.stdout.write(f"  Transcribed:         {s(str(transcribed))}  ({e(str(not_transcribed)) if not_transcribed else s('0')} pending)")
        self.stdout.write(f"  With timestamps:     {timecoded}")
        self.stdout.write(f"  With concepts:       {with_concepts}")

        if methods:
            self.stdout.write("")
            self.stdout.write(w("=== Transcription Methods ==="))
            for m in methods:
                self.stdout.write(f"  {m['transcription_method']:<30} {m['n']}")

        self.stdout.write("")
