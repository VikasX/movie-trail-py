# FILE PURPOSE: Account preferences and hashed one-time email tokens. Django still owns the User
# table.
# Import settings from django.conf (Django framework/database/security helpers).
from django.conf import settings

# Import models from django.db (Django framework/database/security helpers).
from django.db import models


# One preference row per Django user; the one-to-one relationship prevents duplicate profiles.
class UserPreferences(models.Model):
    # Only one such row is allowed per linked parent. If the linked parent is deleted, delete
    # this dependent row too.
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, declare the OneToOneField database field/rule shown below;
    # this declaration itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Set display_name: declare the CharField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 80 characters; Django form validation
    # permits an empty value.
    display_name = models.CharField(max_length=80, blank=True)
    # Set display_language: declare the CharField database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 20 characters; default is 'en-US'.
    display_language = models.CharField(max_length=20, default="en-US")
    # region holds the chosen country code or its corresponding provider-data section. Next,
    # declare the CharField database field/rule shown below; this declaration itself does not run
    # a migration.
    # FIELD DETAILS: Stores text in one column; maximum 2 characters; default is 'IN'.
    region = models.CharField(max_length=2, default="IN")
    # Set updated_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; Django
    # sets this on normal model save calls.
    updated_at = models.DateTimeField(auto_now=True)

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{type(self).__name__} {self.pk}'.
        return f"{type(self).__name__} {self.pk}"


# Hashed one-time verification/reset tokens with expiry and consumption timestamps.
class AccountToken(models.Model):
    # If the linked parent is deleted, delete this dependent row too.
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, declare the ForeignKey database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores a relationship to the parent model shown, not a duplicate of all its
    # fields.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # purpose holds whether this one-time token verifies an email or resets a password. Next,
    # declare the CharField database field/rule shown below; this declaration itself does not run
    # a migration.
    # FIELD DETAILS: Stores text in one column; maximum 20 characters; choices restrict the
    # intended values in Django validation/forms.
    purpose = models.CharField(max_length=20, choices=[("verify", "verify"), ("reset", "reset")])
    # One-way token fingerprint used for lookup; it cannot recreate the original token.
    # Set token_hash: declare the CharField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 64 characters; database uniqueness
    # prevents two rows using the same value.
    token_hash = models.CharField(max_length=64, unique=True)
    # Expiry limits how long a token, lease or retry receipt can be reused.
    # Set expires_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; the
    # declared index helps lookups by this column.
    expires_at = models.DateTimeField(db_index=True)
    # Marks an email token as spent so the same token cannot be used again.
    # Set consumed_at: declare the DateTimeField database field/rule shown below; this declaration
    # itself does not run a migration.
    # FIELD DETAILS: Stores a timestamp; the application works with timezone-aware dates; SQL NULL
    # is permitted for an unknown/not-yet-set value; Django form validation permits an empty
    # value.
    consumed_at = models.DateTimeField(null=True, blank=True)

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: evaluate f'{type(self).__name__} {self.pk}'.
        return f"{type(self).__name__} {self.pk}"
