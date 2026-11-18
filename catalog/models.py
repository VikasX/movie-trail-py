# FILE PURPOSE: Referenced title summaries and short-lived refresh locks; not a copy of all TMDB
# titles.
# Import models from django.db (Django framework/database/security helpers).
from django.db import models


# Minimal metadata for a referenced movie/TV identity, not an imported catalogue.
class TitleSnapshot(models.Model):
    # Set media_type: declare the CharField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 5 characters; choices restrict the
    # intended values in Django validation/forms.
    media_type = models.CharField(max_length=5, choices=[("movie", "Movie"), ("tv", "TV")])
    # Set tmdb_id: declare the PositiveIntegerField database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a nonnegative integer; extra model constraints may require it to be
    # strictly positive.
    tmdb_id = models.PositiveIntegerField()
    # Normalized JSON card fields captured when a referenced title is saved or refreshed.
    # Set summary: declare the JSONField database field/rule shown below; this declaration itself
    # does not run a migration.
    # FIELD DETAILS: Stores structured JSON rather than one plain string; application code still
    # validates its shape; default callable dict supplies a fresh value when a row is created.
    summary = models.JSONField(default=dict)
    # Canonical genre names make saved-data grouping independent of movie/TV genre-number
    # differences.
    # Set genre_keys: declare the JSONField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores structured JSON rather than one plain string; application code still
    # validates its shape; default callable list supplies a fresh value when a row is created.
    genre_keys = models.JSONField(default=list)
    # Reserved minimal metadata; current mood rules do not invent or require keyword IDs.
    # Set keyword_ids: declare the JSONField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores structured JSON rather than one plain string; application code still
    # validates its shape; default callable list supplies a fresh value when a row is created.
    keyword_ids = models.JSONField(default=list)
    # Set adult: declare the BooleanField database field/rule shown below; this declaration itself
    # does not run a migration.
    # FIELD DETAILS: Stores a true/false flag; default is False.
    adult = models.BooleanField(default=False)
    # Set fetched_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; the
    # declared index helps lookups by this column; Django sets this on normal model save calls.
    fetched_at = models.DateTimeField(auto_now=True, db_index=True)
    # Set metadata_status: declare the CharField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 12 characters; default is 'available'.
    metadata_status = models.CharField(max_length=12, default="available")

    # Database-level rules and lookup indexes for the surrounding model, rather than another
    # application table.
    class Meta:
        # Enforce uniqueness/valid combinations in the database, including under concurrent
        # requests.
        # Set constraints: build an ordered list of 2 entries.
        constraints = [
            models.UniqueConstraint(fields=["media_type", "tmdb_id"], name="title_identity_unique"),
            models.CheckConstraint(
                condition=models.Q(media_type__in=["movie", "tv"], tmdb_id__gt=0),
                name="valid_title_identity",
            ),
        ]

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{self.media_type}:{self.tmdb_id}'.
        return f"{self.media_type}:{self.tmdb_id}"


# A short database coordination lock, separate from the cached TMDB response itself.
class CacheLease(models.Model):
    # Set key: declare the CharField database field/rule shown below; this declaration itself does
    # not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 64 characters; this column identifies the
    # row itself.
    key = models.CharField(max_length=64, primary_key=True)
    # Expiry limits how long a token, lease or retry receipt can be reused.
    # Set expires_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; the
    # declared index helps lookups by this column.
    expires_at = models.DateTimeField(db_index=True)
    # owner holds a random identifier that distinguishes our refresh lease from another worker
    # lease. Next, declare the UUIDField database field/rule shown below; this declaration itself
    # does not run a migration.
    # FIELD DETAILS: Stores a UUID rather than a human-entered name.
    owner = models.UUIDField()

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{type(self).__name__} {self.pk}'.
        return f"{type(self).__name__} {self.pk}"
