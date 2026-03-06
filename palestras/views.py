from django.db.models import Q
from django.http import JsonResponse, Http404

from .models import Author, Palestra


def _author_data(author):
    return {
        "name": author.name,
        "photo_url": f"/media/{author.photo}" if author.photo else None,
    }


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


def authors_list(request):
    authors = Author.objects.order_by("name").values("name", "slug")
    return JsonResponse({"authors": list(authors)})


def languages_list(request):
    raw = (
        Palestra.objects.exclude(language__isnull=True)
        .exclude(language="")
        .values_list("language", flat=True)
    )
    langs = set()
    for val in raw:
        for lang in val.split(","):
            lang = lang.strip()
            if lang:
                langs.add(lang)
    return JsonResponse({"languages": sorted(langs)})


def palestra_detail(request, slug):
    try:
        p = Palestra.objects.prefetch_related("authors", "tracks").get(slug=slug)
    except Palestra.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    tracks = []
    for t in p.tracks.all():
        if t.local_path:
            audio_url = f"/media/{t.local_path}"
        else:
            audio_url = t.mp3_url
        tracks.append({
            "id": t.id,
            "name": t.name,
            "audio_url": audio_url,
            "transcription_timecoded": t.transcription_timecoded,
        })

    return JsonResponse({
        "id": p.id,
        "title": p.title,
        "slug": p.slug,
        "url": p.url,
        "description": p.description,
        "categories": p.categories,
        "tags": p.tags,
        "language": p.language,
        "authors": [_author_data(a) for a in p.authors.all()],
        "tracks": tracks,
    })


def search(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))
    per_page = 20
    author_slugs = request.GET.getlist("author")
    selected_languages = request.GET.getlist("language")

    import sys
    print(f"DEBUG search: query={query!r} authors={author_slugs} languages={selected_languages}", file=sys.stderr)

    if not query and not author_slugs and not selected_languages:
        return JsonResponse({"results": [], "total": 0, "page": 1, "pages": 1})

    words = query.split() if query else []
    fields = request.GET.getlist("fields")

    FIELD_MAP = {
        "title": "title__icontains",
        "description": "description__icontains",
        "categories": "categories__icontains",
        "tags": "tags__icontains",
        "transcriptions": "tracks__transcription__icontains",
    }

    active_fields = {k: v for k, v in FIELD_MAP.items() if k in fields} if fields else FIELD_MAP

    qs = Palestra.objects.prefetch_related("authors", "tracks")

    for word in words:
        word_q = Q()
        for lookup in active_fields.values():
            word_q |= Q(**{lookup: word})
        qs = qs.filter(word_q)

    if author_slugs:
        qs = qs.filter(authors__slug__in=author_slugs)

    if selected_languages:
        selected_set = set(selected_languages)
        all_raw = (
            Palestra.objects.exclude(language__isnull=True)
            .exclude(language="")
            .values_list("language", flat=True)
            .distinct()
        )
        matching_raw = {
            raw for raw in all_raw
            if {p.strip() for p in raw.split(",")} & selected_set
        }
        qs = qs.filter(language__in=matching_raw) if matching_raw else qs.none()

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
                "language": p.language,
                "authors": [_author_data(a) for a in p.authors.all()],
                "track_count": p.tracks.count(),
                "transcription_snippets": transcription_snippets,
            }
        )

    return JsonResponse(
        {"results": results, "total": total, "page": page, "pages": pages}
    )
