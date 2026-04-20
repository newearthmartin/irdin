import logging
import re
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from tqdm import tqdm

from palestras.models import AudioTrack

logger = logging.getLogger(__name__)

TRANSCRIPTIONS_DIR = Path(settings.BASE_DIR) / "transcriptions"

LANGUAGE_MAP = {
    "português": "pt",
    "espanhol": "es",
    "inglês": "en",
    "francês": "fr",
    "italiano": "it",
    "alemão": "de",
}


def _palestra_language(track):
    """Return ISO language code for the track's palestra, or None for auto-detect."""
    lang = track.palestra.language.strip() if track.palestra.language else ""
    if not lang or "," in lang:
        return None
    return LANGUAGE_MAP.get(lang.lower())


MLX_MODEL_MAP = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
}

DEFAULT_MODELS = {
    "faster-whisper": "large-v3-turbo",
    "mlx-whisper": "mlx-community/whisper-large-v3-turbo",
    "groq": "whisper-large-v3-turbo",
}


def _audio_duration(audio_path):
    """Return audio duration in seconds via ffprobe, or 0 on failure."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True,
    )
    try:
        return float(probe.stdout.strip())
    except ValueError:
        return 0


def _make_progress_bar(total_secs):
    """Create a tqdm progress bar for audio transcription."""
    total = int(total_secs) if total_secs else None
    bar_format = (
        "{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}s [{elapsed}<{remaining}, {rate_noinv_fmt}]"
        if total_secs else
        "{desc}: {n_fmt}s [{elapsed}, {rate_noinv_fmt}]"
    )
    return tqdm(total=total, unit="s", desc="  progress", leave=False, bar_format=bar_format)


def _build_transcript(segments, bar=None):
    """
    Build plain and timecoded transcripts from a (start_secs, end_secs, text) iterable.
    Optionally updates a tqdm bar as segments are consumed.
    Returns (plain_text, timecoded_text, duration_secs).
    """
    plain_parts = []
    timecoded_parts = []
    duration_secs = 0
    for start, end, text in segments:
        if not text:
            continue
        plain_parts.append(text)
        h = int(start // 3600)
        m = int((start % 3600) // 60)
        s = start % 60
        timecoded_parts.append(f"[{h:02d}:{m:02d}:{s:06.3f}] {text}")
        duration_secs = end
        if bar is not None:
            bar.update(int(end) - bar.n)
    return " ".join(plain_parts), "\n".join(timecoded_parts), duration_secs


class Command(BaseCommand):
    help = "Transcribe downloaded audio tracks using faster-whisper or mlx-whisper"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=0, help="Max tracks to transcribe (0=all)"
        )
        parser.add_argument(
            "--offset", type=int, default=0, help="Skip the first N pending tracks (for parallel runs)"
        )
        parser.add_argument(
            "--model", type=str, default=None, help="Whisper model name"
        )
        parser.add_argument(
            "--backend",
            type=str,
            choices=["faster-whisper", "mlx-whisper", "groq"],
            default=getattr(settings, "TRANSCRIBE_BACKEND", "faster-whisper"),
            help="Transcription backend (default: faster-whisper)",
        )
        parser.add_argument(
            "--retranscribe",
            action="store_true",
            help="Re-transcribe tracks done with a different method",
        )
        parser.add_argument(
            "--pk", type=str, default=None, help="Transcribe specific track(s) by primary key (e.g. 1 or 1,2,3)"
        )

    def _resolve_mlx_model(self, model_name):
        """Map short model names to MLX HF repos, pass through full repo names."""
        if "/" in model_name:
            return model_name
        return MLX_MODEL_MAP.get(model_name, f"mlx-community/whisper-{model_name}-mlx")

    def _transcribe_faster_whisper(self, audio_path, model, model_name, language=None):
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            condition_on_previous_text=False,
            vad_filter=True,
        )
        bar = _make_progress_bar(info.duration)
        plain_text, timecoded_text, _ = _build_transcript(
            ((seg.start, seg.end, seg.text.strip()) for seg in segments), bar
        )
        bar.close()
        return plain_text, timecoded_text, info.duration

    def _transcribe_mlx_whisper(self, audio_path, model_name, language=None):
        import mlx_whisper

        total_secs = _audio_duration(audio_path)
        seg_pattern = re.compile(r"^\[[\d:.]+ --> ([\d:.]+)\]")

        def _parse_ts(ts):
            parts = ts.split(":")
            return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))

        bar = _make_progress_bar(total_secs)
        real_stdout = sys.stdout

        class SegmentInterceptor:
            def write(self, text):
                m = seg_pattern.match(text.strip())
                if m:
                    end_secs = _parse_ts(m.group(1))
                    bar.update(int(end_secs) - bar.n)
            def flush(self):
                pass

        sys.stdout = SegmentInterceptor()
        try:
            result = mlx_whisper.transcribe(
                str(audio_path),
                language=language,
                path_or_hf_repo=model_name,
                condition_on_previous_text=False,
                verbose=True,
            )
        finally:
            sys.stdout = real_stdout
            bar.close()

        segments = result.get("segments", [])
        plain_text, timecoded_text, duration_secs = _build_transcript(
            (seg["start"], seg["end"], seg["text"].strip()) for seg in segments
        )
        return plain_text, timecoded_text, duration_secs

    def _transcribe_groq(self, audio_path, model_name, language=None):
        import time
        from groq import Groq, RateLimitError

        client = Groq(api_key=settings.GROQ_API_KEY)

        def transcribe_chunk(chunk_path):
            kwargs = dict(file=None, model=model_name, response_format="verbose_json",
                          timestamp_granularities=["segment"])
            if language:
                kwargs["language"] = language
            while True:
                try:
                    with open(chunk_path, "rb") as f:
                        kwargs["file"] = f
                        response = client.audio.transcriptions.create(**kwargs)
                    return [(seg["start"], seg["end"], seg["text"].strip())
                            for seg in (response.segments or [])]
                except RateLimitError as e:
                    msg = str(e)
                    m = re.search(r"try again in (\d+)m(\d+)s", msg)
                    if m:
                        wait = int(m.group(1)) * 60 + int(m.group(2)) + 5
                    else:
                        m = re.search(r"try again in (\d+)s", msg)
                        wait = int(m.group(1)) + 5 if m else 60
                    tqdm.write(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)

        return self._transcribe_chunked(audio_path, 25 * 1024 * 1024, 1200, transcribe_chunk)

    def _transcribe_chunked(self, audio_path, size_limit, chunk_secs, transcribe_chunk_fn):
        """
        Split audio if > size_limit bytes and call transcribe_chunk_fn per chunk.
        transcribe_chunk_fn(chunk_path) -> [(start, end, text), ...]
        Returns (plain_text, timecoded_text, total_duration_secs).
        """
        import os, shutil
        needs_split = os.path.getsize(audio_path) > size_limit
        chunks = self._split_audio(audio_path, chunk_secs=chunk_secs) if needs_split else [(audio_path, 0)]
        all_plain = []
        all_timecoded = []
        total_duration = 0
        for i, (chunk_path, chunk_offset) in enumerate(chunks):
            is_last = i == len(chunks) - 1
            for start, end, text in transcribe_chunk_fn(chunk_path):
                if not is_last and start >= chunk_secs:
                    continue
                abs_start = chunk_offset + start
                all_plain.append(text)
                h = int(abs_start // 3600)
                m = int((abs_start % 3600) // 60)
                s = abs_start % 60
                all_timecoded.append(f"[{h:02d}:{m:02d}:{s:06.3f}] {text}")
                total_duration = chunk_offset + end
        if needs_split:
            shutil.rmtree(os.path.dirname(chunks[0][0]), ignore_errors=True)
        return " ".join(all_plain), "\n".join(all_timecoded), total_duration

    def _split_audio(self, audio_path, chunk_secs=1200, overlap_secs=15):
        """Split audio into overlapping chunks using ffmpeg, returning (chunk_path, offset_secs) list."""
        import tempfile

        total_secs = _audio_duration(audio_path)
        tmpdir = tempfile.mkdtemp()
        chunks = []
        offset = 0
        while offset < total_secs:
            chunk_path = f"{tmpdir}/chunk_{offset:06d}.mp3"
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(offset), "-i", audio_path,
                 "-t", str(chunk_secs + overlap_secs), "-c", "copy", chunk_path],
                capture_output=True,
            )
            chunks.append((chunk_path, offset))
            offset += chunk_secs
        return chunks

    def handle(self, *args, **options):
        limit = options["limit"]
        offset = options["offset"]
        backend = options["backend"]
        model_name = options["model"] or DEFAULT_MODELS[backend]
        retranscribe = options["retranscribe"]
        pk = options["pk"]

        if backend == "mlx-whisper":
            model_name = self._resolve_mlx_model(model_name)

        method = f"{backend}:{model_name}"

        if pk:
            pks = [int(p) for p in pk.split(",")]
            qs = AudioTrack.objects.filter(pk__in=pks).exclude(local_path=None)
        else:
            qs = AudioTrack.objects.exclude(local_path=None)
            if retranscribe:
                qs = qs.exclude(transcription_method=method)
            else:
                qs = qs.filter(transcribed_on__isnull=True)

        pending = [t for t in qs if Path(settings.MEDIA_ROOT / t.local_path.name).exists()]
        if offset:
            pending = pending[offset:]
        if limit:
            pending = pending[:limit]
        logger.info(f"Found {len(pending)} tracks to transcribe with {method}")

        if not pending:
            return

        preloaded_model = None
        if backend == "faster-whisper":
            from faster_whisper import WhisperModel

            logger.info(f"Loading model {model_name}...")
            preloaded_model = WhisperModel(model_name, device="auto", compute_type="auto")
            logger.info("Model loaded.")
        elif backend == "groq":
            logger.info(f"Using Groq API with model {model_name}")
        else:
            logger.info(f"Using mlx-whisper with model {model_name}")

        TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)

        for i, track in enumerate(pending, 1):
            logger.info(f"[{i}/{len(pending)}] {track.name}")

            audio_path = Path(track.local_path.path)
            if not audio_path.exists():
                tqdm.write(f"File not found: {audio_path}")
                continue

            language = _palestra_language(track)
            t0 = time.monotonic()
            try:
                if backend == "faster-whisper":
                    plain_text, timecoded_text, duration_secs = (
                        self._transcribe_faster_whisper(audio_path, preloaded_model, model_name, language)
                    )
                elif backend == "groq":
                    plain_text, timecoded_text, duration_secs = (
                        self._transcribe_groq(audio_path, model_name, language)
                    )
                else:
                    plain_text, timecoded_text, duration_secs = (
                        self._transcribe_mlx_whisper(audio_path, model_name, language)
                    )
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

            words = len(plain_text.split())
            elapsed = time.monotonic() - t0
            tqdm.write(f"  finished: {duration_secs:.0f}s audio, {words} words, transcribed in {elapsed:.0f}s")

        total_done = AudioTrack.objects.filter(transcribed_on__isnull=False).count()
        total = AudioTrack.objects.exclude(local_path=None).count()
        logger.info(f"Done. Transcribed: {total_done}/{total}")
