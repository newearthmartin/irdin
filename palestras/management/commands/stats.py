import logging

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from palestras.models import AudioTrack, Author, Palestra

logger = logging.getLogger(__name__)


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

        logger.info("")
        logger.info("=== Palestras ===")
        logger.info(f"  Total:               {total_palestras}")
        logger.info(f"  Scraped:             {scraped}  ({total_palestras - scraped} pending)")
        logger.info(f"  With description:    {with_description}")
        logger.info(f"  Without tracks:      {no_tracks}")

        logger.info("")
        logger.info("=== Authors ===")
        logger.info(f"  Total:               {total_authors}")
        logger.info(f"  With photo:          {with_photo}  ({total_authors - with_photo} without)")

        logger.info("")
        logger.info("=== Audio Tracks ===")
        logger.info(f"  Total:               {total_tracks}")
        logger.info(f"  Downloaded:          {downloaded}  ({not_downloaded} missing)")
        logger.info(f"  Transcribed:         {transcribed}  ({not_transcribed} pending)")
        logger.info(f"  With timestamps:     {timecoded}")
        logger.info(f"  With concepts:       {with_concepts}")

        if methods:
            logger.info("")
            logger.info("=== Transcription Methods ===")
            for m in methods:
                logger.info(f"  {m['transcription_method']:<30} {m['n']}")

        logger.info("")
