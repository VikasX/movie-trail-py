# FILE PURPOSE: Database schema history. Django runs these recorded steps through manage.py
# migrate, not during API requests. Do not casually rewrite an already-applied migration.
# Import call_command from django.core.management (Django framework/database/security helpers).
from django.core.management import call_command

# Import migrations from django.db (Django framework/database/security helpers).
from django.db import migrations


def create_cache(apps, schema_editor):
    # INPUTS TO THIS FUNCTION: apps = argument supplied by the caller; schema_editor = argument
    # supplied by the caller.
    # Call call_command with the inputs shown; its definition explains the checks, side effects
    # and return value.
    call_command(
        "createcachetable", "cinescope_cache", database=schema_editor.connection.alias, verbosity=0
    )


class Migration(migrations.Migration):
    # Set dependencies: build an ordered list of 1 entries.
    dependencies = [("catalog", "0001_initial")]
    # Set operations: build an ordered list of 1 entries.
    operations = [migrations.RunPython(create_cache, migrations.RunPython.noop)]
