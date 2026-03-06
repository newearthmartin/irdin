from django.contrib import admin

from .audio_download import download_tracks, missing_on_disk
from .models import AudioTrack, Author, Palestra


class AudioDownloadedFilter(admin.SimpleListFilter):
    title = "audio downloaded"
    parameter_name = "audio_downloaded"

    def lookups(self, request, model_admin):
        return [
            ("yes", "Downloaded"),
            ("no", "Not downloaded"),
            ("missing", "Marked downloaded but file missing"),
            ("none", "No audio track"),
        ]

    def queryset(self, request, queryset):
        if self.value() in ("yes", "missing"):
            missing_pids = {t.palestra_id for t in missing_on_disk()}
            qs = queryset.filter(tracks__local_path__isnull=False).distinct()
            if self.value() == "missing":
                qs = qs.filter(pk__in=missing_pids)
            else:
                qs = qs.exclude(pk__in=missing_pids)
            return qs
        if self.value() == "no":
            return queryset.filter(tracks__isnull=False).exclude(tracks__local_path__isnull=False).distinct()
        if self.value() == "none":
            return queryset.filter(tracks__isnull=True)
        return queryset


class AudioTrackInline(admin.TabularInline):
    model = AudioTrack
    extra = 0
    readonly_fields = ("name", "local_path", "transcription", "transcribed_on")


@admin.register(Palestra)
class PalestraAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "scraped_on", "track_count", "categories")
    list_filter = ("scraped_on", "language", "categories", "media_format", AudioDownloadedFilter)
    search_fields = ("title", "slug", "sku", "description")
    filter_horizontal = ("authors",)
    inlines = [AudioTrackInline]
    actions = ["download_audios"]

    @admin.display(description="Tracks")
    def track_count(self, obj):
        return obj.tracks.count()

    @admin.action(description="Download audio files")
    def download_audios(self, request, queryset):
        tracks = pending_tracks(
            AudioTrack.objects.filter(palestra__in=queryset)
        )
        if not tracks:
            self.message_user(request, "All audio files already downloaded.")
            return
        downloaded, errors = download_tracks(tracks)
        msg = f"Downloaded {downloaded} file(s)."
        if errors:
            msg += f" {errors} error(s)."
        self.message_user(request, msg)


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)


@admin.register(AudioTrack)
class AudioTrackAdmin(admin.ModelAdmin):
    list_display = ("name", "palestra", "local_path", "transcribed_on")
    list_filter = ("transcribed_on",)
    search_fields = ("name", "palestra__title")
    actions = ["clear_downloaded_file"]

    @admin.action(description="Clear downloaded file")
    def clear_downloaded_file(self, request, queryset):
        count = 0
        for track in queryset.exclude(local_path=None):
            track.local_path.delete(save=False)
            track.local_path = None
            track.save()
            count += 1
        self.message_user(request, f"Cleared {count} downloaded file(s).")
