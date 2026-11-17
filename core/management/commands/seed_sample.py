from django.core.management.base import BaseCommand

from core.models import SampleRecord


class Command(BaseCommand):
    help = "Create the public sample row if it does not already exist."

    def handle(self, *args, **options):
        _, created = SampleRecord.objects.get_or_create(
            name="CineScope database demo",
            defaults={"message": "Hello from PostgreSQL! CineScope is reading database data."},
        )
        self.stdout.write(
            self.style.SUCCESS("Sample row created." if created else "Sample exists.")
        )
