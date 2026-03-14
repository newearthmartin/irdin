from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, Http404
from django.utils.html import escape

from .db_functions import strip_accents
from .models import Author, Palestra

FRONTEND_INDEX = settings.BASE_DIR / "static" / "frontend" / "index.html"


def _author_data(author):
    photo = str(author.photo) if author.photo else None
    if photo:
        photo_url = photo if photo.startswith('/') else f"/media/{photo}"
    else:
        photo_url = None
    return {
        "name": author.name,
        "photo_url": photo_url,
    }


def _find_snippet(text, words, max_len=200):
    """Return a snippet of text around the first matching word."""
    normalized = strip_accents(text)
    best_idx = -1
    for w in words:
        idx = normalized.find(strip_accents(w))
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


def _split_csv_field(field_name):
    raw = (
        Palestra.objects.exclude(**{f"{field_name}__isnull": True})
        .exclude(**{field_name: ""})
        .values_list(field_name, flat=True)
    )
    values = set()
    for val in raw:
        for item in val.split(","):
            item = item.strip()
            if item:
                values.add(item)
    return sorted(values)


def categories_list(request):
    return JsonResponse({"categories": _split_csv_field("categories")})


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


def palestra_page(request, slug):
    """Serve index.html with Open Graph meta tags for link previews."""
    try:
        p = Palestra.objects.prefetch_related("authors").get(slug=slug)
    except Palestra.DoesNotExist:
        with open(FRONTEND_INDEX) as f:
            return HttpResponse(f.read(), content_type="text/html")

    author_names = ", ".join(a.name for a in p.authors.all())
    og_title = f"{author_names} - {p.title}" if author_names else p.title
    description = p.description[:200].strip() if p.description else ""

    og_tags = f"""
    <meta property="og:type" content="website" />
    <meta property="og:title" content="{escape(og_title)}" />
    <meta property="og:description" content="{escape(description)}" />
    <meta property="og:url" content="{escape(request.build_absolute_uri())}" />"""

    with open(FRONTEND_INDEX) as f:
        html = f.read()

    html = html.replace("</head>", og_tags + "\n  </head>", 1)
    return HttpResponse(html, content_type="text/html")


def search(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))
    per_page = 20
    author_slugs = request.GET.getlist("author")
    selected_languages = request.GET.getlist("language")
    selected_categories = request.GET.getlist("category")

    if not query and not author_slugs and not selected_languages and not selected_categories:
        return JsonResponse({"results": [], "total": 0, "page": 1, "pages": 1})

    words = query.split() if query else []
    fields = request.GET.getlist("fields")

    FIELD_MAP = {
        "title": "title__unaccent_icontains",
        "description": "description__unaccent_icontains",
        "categories": "categories__unaccent_icontains",
        "tags": "tags__unaccent_icontains",
        "track_name": "tracks__name__unaccent_icontains",
        "transcriptions": "tracks__transcription__unaccent_icontains",
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

    for selected, field in ((selected_categories, "categories"),):
        if selected:
            selected_set = set(selected)
            all_raw = Palestra.objects.exclude(**{f"{field}__isnull": True}).exclude(**{field: ""}).values_list(field, flat=True).distinct()
            matching_raw = {raw for raw in all_raw if {v.strip() for v in raw.split(",")} & selected_set}
            qs = qs.filter(**{f"{field}__in": matching_raw}) if matching_raw else qs.none()

    qs = qs.distinct()
    total = qs.count()
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, pages))
    offset = (page - 1) * per_page

    search_transcriptions = "transcriptions" in active_fields
    search_track_name = "track_name" in active_fields

    results = []
    for p in qs[offset : offset + per_page]:
        transcription_snippets = []
        matching_track_names = []
        for track in p.tracks.all():
            has_transcription_snippet = False
            if search_transcriptions and track.transcription:
                snippet = _find_snippet(track.transcription, words)
                if snippet:
                    has_transcription_snippet = True
                    transcription_snippets.append(
                        {"track_name": track.name, "snippet": snippet}
                    )
            if search_track_name and not has_transcription_snippet and words and all(
                strip_accents(word.lower()) in strip_accents(track.name.lower()) for word in words
            ):
                matching_track_names.append(track.name)

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
                "matching_track_names": matching_track_names,
                "transcription_snippets": transcription_snippets,
            }
        )

    return JsonResponse(
        {"results": results, "total": total, "page": page, "pages": pages}
    )
