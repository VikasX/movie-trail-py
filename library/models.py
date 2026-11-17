import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class SavedTitle(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.ForeignKey("catalog.TitleSnapshot", on_delete=models.PROTECT)
    watched = models.BooleanField(default=False)
    saved_at = models.DateTimeField(default=timezone.now)
    watched_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "title"], name="saved_user_title_unique"),
            models.CheckConstraint(
                condition=(
                    models.Q(watched=True, watched_at__isnull=False)
                    | models.Q(watched=False, watched_at__isnull=True)
                ),
                name="watched_timestamp_consistent",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-saved_at"]),
            models.Index(fields=["user", "watched", "-saved_at"]),
        ]

    def __str__(self):
        return f"{type(self).__name__} {self.pk}"


class Collection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("name"), "user", name="collection_owner_name_unique")
        ]
        indexes = [models.Index(fields=["user", "-updated_at"])]

    def __str__(self):
        return self.name


class CollectionMembership(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="memberships")
    saved_title = models.ForeignKey(SavedTitle, on_delete=models.CASCADE)
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["collection", "saved_title"], name="membership_unique")
        ]
        indexes = [models.Index(fields=["collection", "-added_at"])]

    def __str__(self):
        return f"{type(self).__name__} {self.pk}"


class PublicShare(models.Model):
    collection = models.OneToOneField(Collection, on_delete=models.CASCADE, related_name="share")
    token_hash = models.CharField(max_length=64, unique=True)
    encrypted_token = models.TextField()
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{type(self).__name__} {self.pk}"


class RecentTitle(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.ForeignKey("catalog.TitleSnapshot", on_delete=models.PROTECT)
    explored_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "title"], name="recent_user_title_unique")
        ]
        indexes = [models.Index(fields=["user", "-explored_at"])]

    def __str__(self):
        return f"{type(self).__name__} {self.pk}"


class GuestCollectionMapping(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    guest_id = models.UUIDField()
    client_id = models.UUIDField()
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "guest_id", "client_id"], name="guest_collection_source_unique"
            )
        ]

    def __str__(self):
        return f"{type(self).__name__} {self.pk}"


class SyncReceipt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    sync_id = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "sync_id"], name="sync_receipt_unique")
        ]

    def __str__(self):
        return f"{type(self).__name__} {self.pk}"
