from pathlib import Path

import httpx
from django.conf import settings

from .models import AudioTrack

AUDIOS_DIR = Path(settings.MEDIA_ROOT) / "audios"


def pending_tracks(queryset=None):
    """Return tracks whose audio file is missing on disk."""
    if queryset is None:
        queryset = AudioTrack.objects.all()
    return [
        t for t in queryset
        if not t.local_path
        or not (AUDIOS_DIR / Path(t.local_path.name).name).exists()
    ]

def missing_on_disk(queryset=None):
    """Return tracks that have local_path set but the file doesn't exist on disk."""
    if queryset is None:
        queryset = AudioTrack.objects.exclude(local_path=None)
    return [
        t for t in queryset
        if not (AUDIOS_DIR / Path(t.local_path.name).name).exists()
    ]


def download_tracks(tracks, on_progress=None, delay=0):
    """
    Download a list of AudioTrack objects.

    on_progress(track, filename, saved_bytes, error) is called after each attempt.
    Returns (downloaded, errors) counts.
    """
    import time

    AUDIOS_DIR.mkdir(exist_ok=True)
    downloaded = 0
    errors = 0

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for track in tracks:
            filename = track.mp3_url.rstrip("/").split("/")[-1]
            dest = AUDIOS_DIR / filename

            if dest.exists():
                track.local_path = f"audios/{filename}"
                track.save()
                downloaded += 1
                if on_progress:
                    on_progress(track, filename, dest.stat().st_size, None)
                continue

            tmp = dest.with_suffix(".tmp")
            error = None
            try:
                with client.stream("GET", track.mp3_url) as resp:
                    resp.raise_for_status()
                    with open(tmp, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            f.write(chunk)
                tmp.rename(dest)
                track.local_path = f"audios/{filename}"
                track.save()
                downloaded += 1
                if on_progress:
                    on_progress(track, filename, dest.stat().st_size, None)
            except httpx.HTTPError as e:
                error = e
                errors += 1
                if tmp.exists():
                    tmp.unlink()
                if on_progress:
                    on_progress(track, filename, 0, error)

            if delay:
                time.sleep(delay)

    return downloaded, errors
