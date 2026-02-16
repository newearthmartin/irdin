import json

import httpx
from django.core.management.base import BaseCommand

from palestras.models import AudioTrack

SYSTEM_PROMPT = (
    "You are a concept extractor. You receive a lecture transcription and return "
    "ONLY a JSON array of short concept names in Portuguese. No explanation, no "
    "markdown, no commentary — just the raw JSON array. "
    'Example output: ["reencarnação", "caridade", "mediunidade"]'
)

USER_PROMPT = (
    "Extract the main concepts and topics from this lecture. "
    "Reply with ONLY a JSON array of short concept names in Portuguese.\n\n{}"
)


class Command(BaseCommand):
    help = "Extract concepts from transcriptions using Ollama"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=0, help="Max tracks to process (0=all)"
        )
        parser.add_argument(
            "--model", type=str, default="llama3.2", help="Ollama model name"
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        model = options["model"]

        qs = AudioTrack.objects.filter(
            transcribed_on__isnull=False,
            concepts=[],
        )

        if limit:
            qs = qs[:limit]

        pending = list(qs)
        self.stdout.write(f"Found {len(pending)} tracks to extract concepts from")

        if not pending:
            return

        for i, track in enumerate(pending, 1):
            self.stdout.write(f"[{i}/{len(pending)}] {track.name}")

            try:
                concepts = self._extract(track.transcription, model)
            except Exception as e:
                self.stderr.write(f"  Error: {e}")
                continue

            cleaned = []
            for name in concepts:
                name = name.strip().lower()
                if name:
                    cleaned.append(name)

            track.concepts = cleaned
            track.save(update_fields=["concepts"])
            self.stdout.write(f"  -> {len(cleaned)} concepts")

        total_with = AudioTrack.objects.exclude(concepts=[]).count()
        total = AudioTrack.objects.filter(transcribed_on__isnull=False).count()
        self.stdout.write(
            self.style.SUCCESS(f"Done. Tracks with concepts: {total_with}/{total}")
        )

    def _extract(self, transcription, model):
        resp = httpx.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_PROMPT.format(transcription)},
                ],
                "stream": False,
                "format": "json",
            },
            timeout=120,
        )
        resp.raise_for_status()
        text = resp.json()["message"]["content"]
        # Extract JSON list from response
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            self.stderr.write(f"  No JSON list found in response: {text[:200]}")
            return []
        return json.loads(text[start:end])
