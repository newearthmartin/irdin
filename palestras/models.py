from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Palestra(models.Model):
    title = models.CharField(max_length=500, blank=True)
    slug = models.SlugField(max_length=500, unique=True)
    url = models.URLField(max_length=500)
    description = models.TextField(blank=True)
    sku = models.CharField(max_length=255, blank=True)
    categories = models.CharField(max_length=500, blank=True)
    tags = models.CharField(max_length=500, blank=True)
    weight = models.CharField(max_length=100, blank=True)
    dimensions = models.CharField(max_length=100, blank=True)
    media_format = models.CharField(max_length=100, blank=True)
    authors = models.ManyToManyField(Author, blank=True)
    scraped_on = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title or self.slug


class AudioTrack(models.Model):
    palestra = models.ForeignKey(
        Palestra, on_delete=models.CASCADE, related_name="tracks"
    )
    name = models.CharField(max_length=500)
    mp3_url = models.URLField(max_length=500)
    local_path = models.FileField(upload_to="audios", max_length=500, blank=True)
    downloaded = models.BooleanField(default=False)
    transcription = models.TextField(blank=True)
    transcription_method = models.CharField(max_length=100, blank=True)
    transcribed_on = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name
