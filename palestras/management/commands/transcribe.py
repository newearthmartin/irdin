from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from tqdm import tqdm

from palestras.models import AudioTrack

TRANSCRIPTIONS_DIR = Path(settings.BASE_DIR) / "transcriptions"


class Command(BaseCommand):
    help = "Transcribe downloaded audio tracks using faster-whisper"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=0, help="Max tracks to transcribe (0=all)"
        )
        parser.add_argument(
            "--model", type=str, default="large-v3", help="Whisper model name"
        )
        parser.add_argument(
            "--retranscribe",
            action="store_true",
            help="Re-transcribe tracks done with a different method",
        )

    def handle(self, *args, **options):
        from faster_whisper import WhisperModel

        limit = options["limit"]
        model_name = options["model"]
        retranscribe = options["retranscribe"]
        method = f"faster-whisper:{model_name}"

        qs = AudioTrack.objects.filter(downloaded=True)
        if retranscribe:
            qs = qs.exclude(transcription_method=method)
        else:
            qs = qs.filter(transcribed_on__isnull=True)

        if limit:
            qs = qs[:limit]

        pending = list(qs)
        self.stdout.write(f"Found {len(pending)} tracks to transcribe with {method}")

        if not pending:
            return

        self.stdout.write(f"Loading model {model_name}...")
        model = WhisperModel(model_name, device="auto", compute_type="auto")
        self.stdout.write("Model loaded.")

        TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)

        for i, track in enumerate(pending, 1):
            self.stdout.write(f"[{i}/{len(pending)}] {track.name}")

            audio_path = Path(track.local_path.path)
            if not audio_path.exists():
                tqdm.write(f"File not found: {audio_path}")
                continue

            try:
                segments, info = model.transcribe(str(audio_path), language="pt")
                duration = info.duration
                if duration:
                    seg_bar = tqdm(
                        total=int(duration),
                        unit="s",
                        desc="  progress",
                        leave=False,
                        bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}s [{elapsed}<{remaining}]",
                    )
                else:
                    seg_bar = None
                plain_parts = []
                timecoded_parts = []
                for seg in segments:
                    text = seg.text.strip()
                    plain_parts.append(text)
                    h, rem = divmod(int(seg.start), 3600)
                    m, s = divmod(rem, 60)
                    timecoded_parts.append(f"[{h:02d}:{m:02d}:{s:02d}] {text}")
                    if seg_bar:
                        seg_bar.update(int(seg.end) - seg_bar.n)
                if seg_bar:
                    seg_bar.close()
                plain_text = " ".join(plain_parts)
                timecoded_text = "\n".join(timecoded_parts)
            except Exception as e:
                tqdm.write(f"Error on {track.name}: {e}")
                continue

            track.transcription = plain_text
            track.transcription_timecoded = timecoded_text
            track.transcription_method = method
            track.transcribed_on = timezone.now()
            track.save()

            # Save to text files
            txt_name = audio_path.stem + ".txt"
            txt_path = TRANSCRIPTIONS_DIR / txt_name
            txt_path.write_text(plain_text, encoding="utf-8")
            tc_path = TRANSCRIPTIONS_DIR / (audio_path.stem + ".timecoded.txt")
            tc_path.write_text(timecoded_text, encoding="utf-8")

            words = len(text.split())
            tqdm.write(f"{track.name} — {info.duration:.0f}s audio, {words} words")

        total_done = AudioTrack.objects.filter(transcribed_on__isnull=False).count()
        total = AudioTrack.objects.filter(downloaded=True).count()
        self.stdout.write(
            self.style.SUCCESS(f"Done. Transcribed: {total_done}/{total}")
        )
