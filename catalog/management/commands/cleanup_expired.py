from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import AccountToken
from catalog.models import CacheLease, TitleSnapshot
from library.models import SyncReceipt


class Command(BaseCommand):
    help = "Prune expired receipts/tokens/leases and unreferenced title snapshots."

    def handle(self, *args, **options):
        now = timezone.now()
        for model in (AccountToken, CacheLease, SyncReceipt):
            count, _ = model.objects.filter(expires_at__lt=now).delete()
            self.stdout.write(f"{model.__name__}: removed {count} expired rows")
        count, _ = TitleSnapshot.objects.filter(
            savedtitle__isnull=True, recenttitle__isnull=True
        ).delete()
        self.stdout.write(f"TitleSnapshot: removed {count} unreferenced rows")
        # DatabaseCache also bounds/culls expired entries on writes; don't clear
        # live query snapshots or active rate-limit state during maintenance.
        cache.set("maintenance:last_cleanup", now.isoformat(), 86400)
