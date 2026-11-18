# FILE PURPOSE: A small demonstration database table; this is not the movie catalogue.
# Import models from django.db (Django framework/database/security helpers).
from django.db import models


# Small original smoke-test table used to confirm a real database read.
class SampleRecord(models.Model):
    """Public demonstration data used to verify reads through the Django ORM."""

    # name holds a display name or field label; collection names are trimmed and checked for
    # allowed length. Next, declare the CharField database field/rule shown below; this
    # declaration itself does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 100 characters; database uniqueness
    # prevents two rows using the same value.
    name = models.CharField(max_length=100, unique=True)
    # Set message: declare the CharField database field/rule shown below; this declaration itself
    # does not run a migration.
    # FIELD DETAILS: Stores text in one column; maximum 255 characters.
    message = models.CharField(max_length=255)

    # Database-level rules and lookup indexes for the surrounding model, rather than another
    # application table.
    class Meta:
        # Set ordering: build an ordered list of 1 entries.
        ordering = ["id"]

    # Give Django/admin a short readable label for this row; this is not the public API
    # response.
    def __str__(self):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Return the result to the caller: read self.name from the indicated object.
        return self.name
