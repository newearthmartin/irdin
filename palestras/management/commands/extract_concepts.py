import json
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from palestras.llm import call_ollama
from palestras.models import AudioTrack

logger = logging.getLogger(__name__)

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
            "--model", type=str, default=settings.OLLAMA_DEFAULT_MODEL, help="Ollama model name"
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
        logger.info(f"Found {len(pending)} tracks to extract concepts from")

        if not pending:
            return

        for i, track in enumerate(pending, 1):
            logger.info(f"[{i}/{len(pending)}] {track.name}")

            try:
                concepts = self._extract(track.transcription, model)
            except Exception as e:
                logger.error(f"  Error: {e}")
                continue

            cleaned = []
            for name in concepts:
                name = name.strip().lower()
                if name:
                    cleaned.append(name)

            track.concepts = cleaned
            track.save(update_fields=["concepts"])
            logger.info(f"  -> {len(cleaned)} concepts")

        total_with = AudioTrack.objects.exclude(concepts=[]).count()
        total = AudioTrack.objects.filter(transcribed_on__isnull=False).count()
        logger.info(f"Done. Tracks with concepts: {total_with}/{total}")

    def _extract(self, transcription, model):
        data = call_ollama(SYSTEM_PROMPT, USER_PROMPT.format(transcription), model=model)
        if isinstance(data, list):
            return data
        # Try to extract list from dict response
        text = json.dumps(data)
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            logger.error(f"  No JSON list found in response: {text[:200]}")
            return []
        return json.loads(text[start:end])
