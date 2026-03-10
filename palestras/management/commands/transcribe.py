from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from tqdm import tqdm

from palestras.models import AudioTrack

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
    "whisper-cpp": "large-v3-turbo",
    "openai": "gpt-4o-transcribe",
}


class Command(BaseCommand):
    help = "Transcribe downloaded audio tracks using faster-whisper or mlx-whisper"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=0, help="Max tracks to transcribe (0=all)"
        )
        parser.add_argument(
            "--model", type=str, default=None, help="Whisper model name"
        )
        parser.add_argument(
            "--backend",
            type=str,
            choices=["faster-whisper", "mlx-whisper", "groq", "whisper-cpp", "openai"],
            default="faster-whisper",
            help="Transcription backend (default: faster-whisper)",
        )
        parser.add_argument(
            "--retranscribe",
            action="store_true",
            help="Re-transcribe tracks done with a different method",
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
        duration_secs = info.duration
        return plain_text, timecoded_text, duration_secs

    def _transcribe_mlx_whisper(self, audio_path, model_name, language=None):
        import mlx_whisper

        result = mlx_whisper.transcribe(
            str(audio_path),
            language=language,
            path_or_hf_repo=model_name,
            condition_on_previous_text=False,
        )
        segments = result.get("segments", [])
        plain_parts = []
        timecoded_parts = []
        for seg in tqdm(segments, desc="  segments", leave=False):
            text = seg["text"].strip()
            plain_parts.append(text)
            h, rem = divmod(int(seg["start"]), 3600)
            m, s = divmod(rem, 60)
            timecoded_parts.append(f"[{h:02d}:{m:02d}:{s:02d}] {text}")
        plain_text = " ".join(plain_parts)
        timecoded_text = "\n".join(timecoded_parts)
        duration_secs = segments[-1]["end"] if segments else 0
        return plain_text, timecoded_text, duration_secs

    def _transcribe_whisper_cpp(self, audio_path, model):
        segments = model.transcribe(str(audio_path))
        plain_parts = []
        timecoded_parts = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            plain_parts.append(text)
            start_secs = seg.t0 / 100
            h, rem = divmod(int(start_secs), 3600)
            m, s = divmod(rem, 60)
            timecoded_parts.append(f"[{h:02d}:{m:02d}:{s:02d}] {text}")
        plain_text = " ".join(plain_parts)
        timecoded_text = "\n".join(timecoded_parts)
        duration_secs = segments[-1].t1 / 100 if segments else 0
        return plain_text, timecoded_text, duration_secs

    def _transcribe_groq(self, audio_path, model_name, language=None):
        from groq import Groq

        client = Groq()
        kwargs = dict(
            file=None,
            model=model_name,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
        if language:
            kwargs["language"] = language
        with open(audio_path, "rb") as audio_file:
            kwargs["file"] = audio_file
            response = client.audio.transcriptions.create(**kwargs)
        segments = response.segments or []
        plain_parts = []
        timecoded_parts = []
        for seg in segments:
            text = seg["text"].strip()
            plain_parts.append(text)
            h, rem = divmod(int(seg["start"]), 3600)
            m, s = divmod(rem, 60)
            timecoded_parts.append(f"[{h:02d}:{m:02d}:{s:02d}] {text}")
        plain_text = " ".join(plain_parts)
        timecoded_text = "\n".join(timecoded_parts)
        duration_secs = segments[-1]["end"] if segments else 0
        return plain_text, timecoded_text, duration_secs

    def _transcribe_openai(self, audio_path, model_name, language=None):
        from openai import OpenAI

        client = OpenAI()
        kwargs = dict(
            file=None,
            model=model_name,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
        if language:
            kwargs["language"] = language
        with open(audio_path, "rb") as audio_file:
            kwargs["file"] = audio_file
            response = client.audio.transcriptions.create(**kwargs)
        segments = response.segments or []
        plain_parts = []
        timecoded_parts = []
        for seg in segments:
            text = seg["text"].strip()
            plain_parts.append(text)
            h, rem = divmod(int(seg["start"]), 3600)
            m, s = divmod(rem, 60)
            timecoded_parts.append(f"[{h:02d}:{m:02d}:{s:02d}] {text}")
        plain_text = " ".join(plain_parts)
        timecoded_text = "\n".join(timecoded_parts)
        duration_secs = segments[-1]["end"] if segments else 0
        return plain_text, timecoded_text, duration_secs

    def handle(self, *args, **options):
        limit = options["limit"]
        backend = options["backend"]
        model_name = options["model"] or DEFAULT_MODELS[backend]
        retranscribe = options["retranscribe"]

        if backend == "mlx-whisper":
            model_name = self._resolve_mlx_model(model_name)

        method = f"{backend}:{model_name}"

        qs = AudioTrack.objects.exclude(local_path=None)
        if retranscribe:
            qs = qs.exclude(transcription_method=method)
        else:
            qs = qs.filter(transcribed_on__isnull=True)

        pending = [t for t in qs if Path(settings.MEDIA_ROOT / t.local_path.name).exists()]
        if limit:
            pending = pending[:limit]
        self.stdout.write(f"Found {len(pending)} tracks to transcribe with {method}")

        if not pending:
            return

        preloaded_model = None
        if backend == "faster-whisper":
            from faster_whisper import WhisperModel

            self.stdout.write(f"Loading model {model_name}...")
            preloaded_model = WhisperModel(model_name, device="auto", compute_type="auto")
            self.stdout.write("Model loaded.")
        elif backend == "whisper-cpp":
            from pywhispercpp.model import Model

            self.stdout.write(f"Loading model {model_name}...")
            preloaded_model = Model(model_name)
            self.stdout.write("Model loaded.")
        elif backend == "groq":
            self.stdout.write(f"Using Groq API with model {model_name}")
        elif backend == "openai":
            self.stdout.write(f"Using OpenAI API with model {model_name}")
        else:
            self.stdout.write(f"Using mlx-whisper with model {model_name}")

        TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)

        for i, track in enumerate(pending, 1):
            self.stdout.write(f"[{i}/{len(pending)}] {track.name}")

            audio_path = Path(track.local_path.path)
            if not audio_path.exists():
                tqdm.write(f"File not found: {audio_path}")
                continue

            language = _palestra_language(track)
            try:
                if backend == "faster-whisper":
                    plain_text, timecoded_text, duration_secs = (
                        self._transcribe_faster_whisper(audio_path, preloaded_model, model_name, language)
                    )
                elif backend == "whisper-cpp":
                    plain_text, timecoded_text, duration_secs = (
                        self._transcribe_whisper_cpp(audio_path, preloaded_model)
                    )
                elif backend == "groq":
                    plain_text, timecoded_text, duration_secs = (
                        self._transcribe_groq(audio_path, model_name, language)
                    )
                elif backend == "openai":
                    plain_text, timecoded_text, duration_secs = (
                        self._transcribe_openai(audio_path, model_name, language)
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
            tqdm.write(f"{track.name} — {duration_secs:.0f}s audio, {words} words")

        total_done = AudioTrack.objects.filter(transcribed_on__isnull=False).count()
        total = AudioTrack.objects.exclude(local_path=None).count()
        self.stdout.write(
            self.style.SUCCESS(f"Done. Transcribed: {total_done}/{total}")
        )
