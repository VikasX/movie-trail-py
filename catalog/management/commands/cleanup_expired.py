# FILE PURPOSE: Explicit maintenance command; deletes expired/unreferenced rows when an operator
# runs it.
# Import cache from django.core.cache (Django framework/database/security helpers).
from django.core.cache import cache

# Import BaseCommand from django.core.management.base (Django framework/database/security
# helpers).
from django.core.management.base import BaseCommand

# Import timezone from django.utils (Django framework/database/security helpers).
from django.utils import timezone

# Import AccountToken from accounts.models (our account layer).
from accounts.models import AccountToken

# Import CacheLease, TitleSnapshot from catalog.models (our TMDB/normalization layer).
from catalog.models import CacheLease, RateLimitBucket, TitleSnapshot

# Import SyncReceipt from library.models (our personal-library layer).
from library.models import SyncReceipt


class Command(BaseCommand):
    # Set help: use the fixed value 'Prune expired receipts/tokens/leases and unreferenced title
    # snapshots.'.
    help = "Prune expired receipts/tokens/leases and unreferenced title snapshots."

    # Run this management command only when it is explicitly requested from a terminal.
    def handle(self, *args, **options):
        # INPUTS TO THIS FUNCTION: self = this class instance.
        # now holds one server timestamp shared by related changes in this action. Next, call
        # timezone.now with the inputs shown; its definition explains the checks, side effects and
        # return value.
        now = timezone.now()
        # Repeat the following block for each model from (AccountToken, CacheLease, SyncReceipt).
        # Each iteration handles that one item/pair.
        for model in (AccountToken, CacheLease, RateLimitBucket, SyncReceipt):
            # Set (count, _): delete the selected row(s), applying their configured related-row
            # deletion rules.
            count, _ = model.objects.filter(expires_at__lt=now).delete()
            # Call self.stdout.write with the inputs shown; its definition explains the checks,
            # side effects and return value.
            self.stdout.write(f"{model.__name__}: removed {count} expired rows")
        # Set (count, _): delete the selected row(s), applying their configured related-row
        # deletion rules.
        count, _ = TitleSnapshot.objects.filter(
            savedtitle__isnull=True, recenttitle__isnull=True
        ).delete()
        # Call self.stdout.write with the inputs shown; its definition explains the checks, side
        # effects and return value.
        self.stdout.write(f"TitleSnapshot: removed {count} unreferenced rows")
        # DatabaseCache also bounds/culls expired entries on writes; don't clear
        # live query snapshots or active rate-limit state during maintenance.
        # Remember this value for the specified lifetime.
        cache.set("maintenance:last_cleanup", now.isoformat(), 86400)
