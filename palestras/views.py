from django.db.models import Q
from django.http import JsonResponse

from .models import Palestra


def _find_snippet(text, words, max_len=200):
    """Return a snippet of text around the first matching word."""
    lower = text.lower()
    best_idx = -1
    for w in words:
        idx = lower.find(w.lower())
        if idx != -1:
            best_idx = idx
            break
    if best_idx == -1:
        return None
    start = max(0, best_idx - max_len // 2)
    end = min(len(text), start + max_len)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def search(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))
    per_page = 20

    if not query:
        return JsonResponse({"results": [], "total": 0, "page": 1, "pages": 1})

    words = query.split()
    fields = request.GET.getlist("fields")

    FIELD_MAP = {
        "title": "title__icontains",
        "description": "description__icontains",
        "categories": "categories__icontains",
        "tags": "tags__icontains",
        "authors": "authors__name__icontains",
        "transcriptions": "tracks__transcription__icontains",
    }

    active_fields = {k: v for k, v in FIELD_MAP.items() if k in fields} if fields else FIELD_MAP

    qs = Palestra.objects.prefetch_related("authors", "tracks")

    for word in words:
        word_q = Q()
        for lookup in active_fields.values():
            word_q |= Q(**{lookup: word})
        qs = qs.filter(word_q)

    qs = qs.distinct()
    total = qs.count()
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, pages))
    offset = (page - 1) * per_page

    search_transcriptions = "transcriptions" in active_fields

    results = []
    for p in qs[offset : offset + per_page]:
        transcription_snippets = []
        if search_transcriptions:
            for track in p.tracks.all():
                if not track.transcription:
                    continue
                snippet = _find_snippet(track.transcription, words)
                if snippet:
                    transcription_snippets.append(
                        {"track_name": track.name, "snippet": snippet}
                    )

        results.append(
            {
                "id": p.id,
                "title": p.title,
                "slug": p.slug,
                "url": p.url,
                "description": p.description,
                "categories": p.categories,
                "tags": p.tags,
                "authors": [a.name for a in p.authors.all()],
                "track_count": p.tracks.count(),
                "transcription_snippets": transcription_snippets,
            }
        )

    return JsonResponse(
        {"results": results, "total": total, "page": page, "pages": pages}
    )
