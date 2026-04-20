import logging
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from palestras.models import AudioTrack, Author, Clip

logger = logging.getLogger(__name__)

MEDIA_FIELDS = [
    (AudioTrack, "local_path", "audios"),
    (Author, "photo", "author_photos"),
]


class Command(BaseCommand):
    help = "Remove media files not referenced by any database record"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="List orphans without deleting"
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        total_deleted = 0
        total_bytes = 0

        for model, field_name, subdir in MEDIA_FIELDS:
            media_dir = Path(settings.MEDIA_ROOT) / subdir
            if not media_dir.exists():
                continue

            db_files = set()
            qs = model.objects.exclude(**{field_name: ""}).exclude(
                **{f"{field_name}__isnull": True}
            )
            for path in qs.values_list(field_name, flat=True):
                db_files.add(os.path.basename(path))

            disk_files = set(f for f in os.listdir(media_dir) if not f.startswith("."))
            orphans = sorted(disk_files - db_files)

            if not orphans:
                logger.info(f"{subdir}/: clean ({len(disk_files)} files)")
                continue

            orphan_size = sum(
                os.path.getsize(media_dir / f) for f in orphans
            )
            size_mb = orphan_size / 1024 / 1024

            action = "would delete" if dry_run else "deleting"
            logger.info(
                f"{subdir}/: {len(orphans)} orphans ({size_mb:.1f} MB), "
                f"{action}..."
            )

            for f in orphans:
                if not dry_run:
                    os.remove(media_dir / f)
                logger.info(f"  {f}")

            total_deleted += len(orphans)
            total_bytes += orphan_size

        total_mb = total_bytes / 1024 / 1024
        prefix = "Would delete" if dry_run else "Deleted"
        logger.info(f"\n{prefix} {total_deleted} orphan files ({total_mb:.1f} MB)")
