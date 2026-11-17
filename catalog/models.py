from django.db import models


class TitleSnapshot(models.Model):
    media_type = models.CharField(max_length=5, choices=[("movie", "Movie"), ("tv", "TV")])
    tmdb_id = models.PositiveIntegerField()
    summary = models.JSONField(default=dict)
    genre_keys = models.JSONField(default=list)
    keyword_ids = models.JSONField(default=list)
    adult = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(auto_now=True, db_index=True)
    metadata_status = models.CharField(max_length=12, default="available")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["media_type", "tmdb_id"], name="title_identity_unique"),
            models.CheckConstraint(
                condition=models.Q(media_type__in=["movie", "tv"], tmdb_id__gt=0),
                name="valid_title_identity",
            ),
        ]

    def __str__(self):
        return f"{self.media_type}:{self.tmdb_id}"


class CacheLease(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField(db_index=True)
    owner = models.UUIDField()

    def __str__(self):
        return f"{type(self).__name__} {self.pk}"
