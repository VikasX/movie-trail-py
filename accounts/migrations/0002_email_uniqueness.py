from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower


def audit_emails(apps, schema_editor):
    user = apps.get_model("auth", "User")
    duplicates = (
        user.objects.using(schema_editor.connection.alias)
        .exclude(email="")
        .annotate(normalized=Lower("email"))
        .values("normalized")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError(
            "Existing users have duplicate case-insensitive emails. "
            "Resolve them before migrating; no data was deleted."
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.RunPython(audit_emails, migrations.RunPython.noop),
        migrations.RunSQL(
            "CREATE UNIQUE INDEX cinescope_user_email_unique "
            "ON auth_user (LOWER(email)) WHERE email <> ''",
            "DROP INDEX cinescope_user_email_unique",
        ),
    ]
