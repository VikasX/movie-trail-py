# FILE PURPOSE: Explicit terminal command to insert the sample row safely; never runs per
# request.
# Import BaseCommand from django.core.management.base (Django framework/database/security
# helpers).
from django.core.management.base import BaseCommand

# Import SampleRecord from core.models (the named Python helper module).
from core.models import SampleRecord


class Command(BaseCommand):
    # Set help: use the fixed value 'Create the public sample row if it does not already exist.'.
    help = "Create the public sample row if it does not already exist."

    # Run this management command only when it is explicitly requested from a terminal.
    def handle(self, *args, **options):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # Set (_, created): reuse a matching row or insert one; the second returned value says
        # whether it was newly created.
        _, created = SampleRecord.objects.get_or_create(
            name="CineScope database demo",
            defaults={"message": "Hello from PostgreSQL! CineScope is reading database data."},
        )
        # Call self.stdout.write with the inputs shown; its definition explains the checks, side
        # effects and return value.
        self.stdout.write(
            self.style.SUCCESS("Sample row created." if created else "Sample exists.")
        )
