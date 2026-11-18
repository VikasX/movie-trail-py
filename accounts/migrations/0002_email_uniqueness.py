# FILE PURPOSE: Database schema history. Django runs these recorded steps through manage.py
# migrate, not during API requests. Do not casually rewrite an already-applied migration.
# Import migrations from django.db (Django framework/database/security helpers).
from django.db import migrations

# Import Count from django.db.models (Django framework/database/security helpers).
from django.db.models import Count

# Import Lower from django.db.models.functions (Django framework/database/security helpers).
from django.db.models.functions import Lower


def audit_emails(apps, schema_editor):
    # INPUTS TO THIS FUNCTION: apps = argument supplied by the caller; schema_editor = argument
    # supplied by the caller.
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, call apps.get_model with the inputs shown; its definition
    # explains the checks, side effects and return value.
    user = apps.get_model("auth", "User")
    # Set duplicates: construct a Django QuerySet restricted to the conditions shown; it remains
    # lazy until evaluated.
    duplicates = (
        user.objects.using(schema_editor.connection.alias)
        .exclude(email="")
        .annotate(normalized=Lower("email"))
        .values("normalized")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    # Enter this branch only when duplicates.exists(). Otherwise execution uses its alternative or
    # continues below.
    if duplicates.exists():
        # Raise RuntimeError; normal execution of this block stops here.
        raise RuntimeError(
            "Existing users have duplicate case-insensitive emails. "
            "Resolve them before migrating; no data was deleted."
        )


class Migration(migrations.Migration):
    # Set dependencies: build an ordered list of 1 entries.
    dependencies = [("accounts", "0001_initial")]
    # Set operations: build an ordered list of 2 entries.
    operations = [
        migrations.RunPython(audit_emails, migrations.RunPython.noop),
        migrations.RunSQL(
            "CREATE UNIQUE INDEX cinescope_user_email_unique "
            "ON auth_user (LOWER(email)) WHERE email <> ''",
            "DROP INDEX cinescope_user_email_unique",
        ),
    ]
