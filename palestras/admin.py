from pathlib import Path

from django.contrib import admin

from .models import AudioTrack, Author, Palestra


class AudioTrackInline(admin.TabularInline):
    model = AudioTrack
    extra = 0
    readonly_fields = ("name", "mp3_url", "local_path", "transcription", "transcribed_on")


@admin.register(Palestra)
class PalestraAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "scraped_on", "track_count", "categories")
    list_filter = ("scraped_on", "categories", "media_format")
    search_fields = ("title", "slug", "sku", "description")
    filter_horizontal = ("authors",)
    inlines = [AudioTrackInline]

    @admin.display(description="Tracks")
    def track_count(self, obj):
        return obj.tracks.count()


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
        for track in queryset.filter(local_path__gt=""):
            track.local_path.delete(save=True)
            count += 1
        self.message_user(request, f"Cleared {count} downloaded file(s).")
