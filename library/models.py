# FILE PURPOSE: Database structure for saved/watched titles, collections, sharing, history and
# guest imports.
# Import uuid so the code below can use that module namespace.
import uuid

# Import settings from django.conf (Django framework/database/security helpers).
from django.conf import settings

# Import models from django.db (Django framework/database/security helpers).
from django.db import models

# Import Lower from django.db.models.functions (Django framework/database/security helpers).
from django.db.models.functions import Lower

# Import timezone from django.utils (Django framework/database/security helpers).
from django.utils import timezone


# One account/title relationship containing watched state; watched is not a second copy of the
# title.
class SavedTitle(models.Model):
    # If the linked parent is deleted, delete this dependent row too.
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, declare the ForeignKey database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Do not delete a referenced parent while application rows still depend on it.
    # title holds a referenced title record or normalized card; this is deliberately separate from
    # an owner SavedTitle row. Next, declare the ForeignKey database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    title = models.ForeignKey("catalog.TitleSnapshot", on_delete=models.PROTECT)
    # A flag on the saved row: marking it watched does not remove it from the library.
    # watched stores whether this saved title has been watched. Next, declare the
    # BooleanField database field/rule shown below; this declaration itself does not run a
    # migration.
    # FIELD DETAILS: Stores a true/false flag; default is False.
    watched = models.BooleanField(default=False)
    # When the account saved this title; guest imports can preserve the original guest time.
    # saved_at stores when this title was saved; guest imports can preserve the guest timestamp.
    # Next, declare the DateTimeField database field/rule shown below; this declaration itself
    # does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; default
    # callable timezone.now supplies a fresh value when a row is created.
    saved_at = models.DateTimeField(default=timezone.now)
    # Must be present only when watched is true; the database also checks this rule.
    # watched_at stores when the title was watched; its presence must agree with
    # watched=true. Next, declare the DateTimeField database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; SQL NULL
    # is permitted for an unknown/not-yet-set value; Django form validation permits an empty
    # value.
    watched_at = models.DateTimeField(null=True, blank=True)
    # Set updated_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; Django
    # sets this on normal model save calls.
    updated_at = models.DateTimeField(auto_now=True)

    # Database-level rules and lookup indexes for the surrounding model, rather than another
    # application table.
    class Meta:
        # Enforce uniqueness/valid combinations in the database, including under concurrent
        # requests.
        # Set constraints: build an ordered list of 2 entries.
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
        # Help PostgreSQL find this account recent/saved/collection rows without scanning every
        # row.
        # Set indexes: build an ordered list of 2 entries.
        indexes = [
            models.Index(fields=["user", "-saved_at"]),
            models.Index(fields=["user", "watched", "-saved_at"]),
        ]

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{type(self).__name__} {self.pk}'.
        return f"{type(self).__name__} {self.pk}"


# A real custom collection owned by one account. Automatic collections never become rows here.
class Collection(models.Model):
    # Set id: declare the UUIDField database field/rule shown below; this declaration itself does
    # not run a migration.
    # FIELD DETAILS: Stores a UUID rather than a human-entered name; this column identifies the
    # row itself; default callable uuid.uuid4 supplies a fresh value when a row is created.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # If the linked parent is deleted, delete this dependent row too.
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, declare the ForeignKey database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # name holds a display name or field label; collection names are trimmed and checked for
    # allowed length. Next, declare the CharField database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 80 characters.
    name = models.CharField(max_length=80)
    # Set created_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; Django
    # sets this only when creating a row.
    created_at = models.DateTimeField(auto_now_add=True)
    # Set updated_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; Django
    # sets this on normal model save calls.
    updated_at = models.DateTimeField(auto_now=True)

    # Database-level rules and lookup indexes for the surrounding model, rather than another
    # application table.
    class Meta:
        # Enforce uniqueness/valid combinations in the database, including under concurrent
        # requests.
        # Set constraints: build an ordered list of 1 entries.
        constraints = [
            models.UniqueConstraint(Lower("name"), "user", name="collection_owner_name_unique")
        ]
        # Help PostgreSQL find this account recent/saved/collection rows without scanning every
        # row.
        # Set indexes: build an ordered list of 1 entries.
        indexes = [models.Index(fields=["user", "-updated_at"])]

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: read self.name from the indicated object.
        return self.name


# Connects a custom collection to a saved title; one saved title may belong to many collections.
class CollectionMembership(models.Model):
    # If the linked parent is deleted, delete this dependent row too.
    # collection holds the account custom collection matched or created for this guest source.
    # Next, declare the ForeignKey database field/rule shown below; this declaration itself does
    # not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="memberships")
    # If the linked parent is deleted, delete this dependent row too.
    # Set saved_title: declare the ForeignKey database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    saved_title = models.ForeignKey(SavedTitle, on_delete=models.CASCADE)
    # Set added_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; default
    # callable timezone.now supplies a fresh value when a row is created.
    added_at = models.DateTimeField(default=timezone.now)

    # Database-level rules and lookup indexes for the surrounding model, rather than another
    # application table.
    class Meta:
        # Enforce uniqueness/valid combinations in the database, including under concurrent
        # requests.
        # Set constraints: build an ordered list of 1 entries.
        constraints = [
            models.UniqueConstraint(fields=["collection", "saved_title"], name="membership_unique")
        ]
        # Help PostgreSQL find this account recent/saved/collection rows without scanning every
        # row.
        # Set indexes: build an ordered list of 1 entries.
        indexes = [models.Index(fields=["collection", "-added_at"])]

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{type(self).__name__} {self.pk}'.
        return f"{type(self).__name__} {self.pk}"


# Stores sharing state, a lookup hash and encrypted recoverable token; raw capabilities are not
# admin fields.
class PublicShare(models.Model):
    # Only one such row is allowed per linked parent. If the linked parent is deleted, delete
    # this dependent row too.
    # collection holds the account custom collection matched or created for this guest source.
    # Next, declare the OneToOneField database field/rule shown below; this declaration itself
    # does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    collection = models.OneToOneField(Collection, on_delete=models.CASCADE, related_name="share")
    # One-way token fingerprint used for lookup; it cannot recreate the original token.
    # Set token_hash: declare the CharField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 64 characters; database uniqueness
    # prevents two rows using the same value.
    token_hash = models.CharField(max_length=64, unique=True)
    # Recoverable ciphertext lets an owner request the same active link again.
    # Set encrypted_token: declare the TextField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores longer text; encrypted-token contents are ciphertext, not plaintext.
    encrypted_token = models.TextField()
    # Set enabled: declare the BooleanField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a true/false flag; default is True.
    enabled = models.BooleanField(default=True)
    # Set created_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; Django
    # sets this only when creating a row.
    created_at = models.DateTimeField(auto_now_add=True)
    # Set revoked_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; SQL NULL
    # is permitted for an unknown/not-yet-set value; Django form validation permits an empty
    # value.
    revoked_at = models.DateTimeField(null=True, blank=True)

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{type(self).__name__} {self.pk}'.
        return f"{type(self).__name__} {self.pk}"


# One most-recent exploration timestamp per account/title pair.
class RecentTitle(models.Model):
    # If the linked parent is deleted, delete this dependent row too.
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, declare the ForeignKey database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Do not delete a referenced parent while application rows still depend on it.
    # title holds a referenced title record or normalized card; this is deliberately separate from
    # an owner SavedTitle row. Next, declare the ForeignKey database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    title = models.ForeignKey("catalog.TitleSnapshot", on_delete=models.PROTECT)
    # Server-recorded time of deliberate exploration; repeated exploration updates the same row.
    # Set explored_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; default
    # callable timezone.now supplies a fresh value when a row is created.
    explored_at = models.DateTimeField(default=timezone.now)

    # Database-level rules and lookup indexes for the surrounding model, rather than another
    # application table.
    class Meta:
        # Enforce uniqueness/valid combinations in the database, including under concurrent
        # requests.
        # Set constraints: build an ordered list of 1 entries.
        constraints = [
            models.UniqueConstraint(fields=["user", "title"], name="recent_user_title_unique")
        ]
        # Help PostgreSQL find this account recent/saved/collection rows without scanning every
        # row.
        # Set indexes: build an ordered list of 1 entries.
        indexes = [models.Index(fields=["user", "-explored_at"])]

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{type(self).__name__} {self.pk}'.
        return f"{type(self).__name__} {self.pk}"


# Remembers which guest collection became which account collection, including deletion
# tombstones.
class GuestCollectionMapping(models.Model):
    # If the linked parent is deleted, delete this dependent row too.
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, declare the ForeignKey database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Identifies one guest browser namespace; it is not a server-side anonymous user.
    # Set guest_id: declare the UUIDField database field/rule shown below; this declaration itself
    # does not run a migration.
    # FIELD DETAILS: Stores a UUID rather than a human-entered name.
    guest_id = models.UUIDField()
    # Stable guest collection UUID; matching by name alone would merge unrelated collections.
    # Set client_id: declare the UUIDField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a UUID rather than a human-entered name.
    client_id = models.UUIDField()
    # If the linked parent is deleted, keep this row and clear the link.
    # collection holds the account custom collection matched or created for this guest source.
    # Next, declare the ForeignKey database field/rule shown below; this declaration itself does
    # not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields; SQL NULL is permitted for an unknown/not-yet-set value.
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True)
    # Preserves deletion intent so a future guest retry does not recreate a removed collection.
    # Set deleted_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; SQL NULL
    # is permitted for an unknown/not-yet-set value; Django form validation permits an empty
    # value.
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Database-level rules and lookup indexes for the surrounding model, rather than another
    # application table.
    class Meta:
        # Enforce uniqueness/valid combinations in the database, including under concurrent
        # requests.
        # Set constraints: build an ordered list of 1 entries.
        constraints = [
            models.UniqueConstraint(
                fields=["user", "guest_id", "client_id"], name="guest_collection_source_unique"
            )
        ]

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{type(self).__name__} {self.pk}'.
        return f"{type(self).__name__} {self.pk}"


# Remembers an import request hash and result so a retry does not repeat its writes.
class SyncReceipt(models.Model):
    # If the linked parent is deleted, delete this dependent row too.
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, declare the ForeignKey database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # The client keeps this UUID unchanged when retrying the same guest-import payload.
    # Set sync_id: declare the UUIDField database field/rule shown below; this declaration itself
    # does not run a migration.
    # FIELD DETAILS: Stores a UUID rather than a human-entered name.
    sync_id = models.UUIDField()
    # Detects a changed payload incorrectly sent with a previously used sync ID.
    # Set request_hash: declare the CharField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 64 characters.
    request_hash = models.CharField(max_length=64)
    # Stores the completed import response, so a retry can return the original counts and
    # mappings.
    # Set result: declare the JSONField database field/rule shown below; this declaration itself
    # does not run a migration.
    # FIELD DETAILS: Stores structured JSON rather than one plain string; application code still
    # validates its shape; default callable dict supplies a fresh value when a row is created.
    result = models.JSONField(default=dict)
    # Set created_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; Django
    # sets this only when creating a row.
    created_at = models.DateTimeField(auto_now_add=True)
    # Expiry limits how long a token, lease or retry receipt can be reused.
    # Set expires_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; the
    # declared index helps lookups by this column.
    expires_at = models.DateTimeField(db_index=True)

    # Database-level rules and lookup indexes for the surrounding model, rather than another
    # application table.
    class Meta:
        # Enforce uniqueness/valid combinations in the database, including under concurrent
        # requests.
        # Set constraints: build an ordered list of 1 entries.
        constraints = [
            models.UniqueConstraint(fields=["user", "sync_id"], name="sync_receipt_unique")
        ]

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{type(self).__name__} {self.pk}'.
        return f"{type(self).__name__} {self.pk}"
