# FILE PURPOSE: Coordinates refresh work through PostgreSQL so multiple Vercel instances do not
# all fetch at once.
# Import hashlib so the code below can use that module namespace.
import hashlib

# Import time so the code below can use that module namespace.
import time

# Import uuid so the code below can use that module namespace.
import uuid

# Import contextmanager from contextlib (the named Python helper module).
from contextlib import contextmanager

# Import timedelta from datetime (the named Python helper module).
from datetime import timedelta

# Import IntegrityError, transaction from django.db (Django framework/database/security helpers).
from django.db import IntegrityError, transaction

# Import timezone from django.utils (Django framework/database/security helpers).
from django.utils import timezone

# Import CacheLease from catalog.models (our TMDB/normalization layer).
from catalog.models import CacheLease

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError


# Acquire a short shared refresh lock, run the protected work, then release only our own lock.
@contextmanager
def lease(key):
    # INPUTS TO THIS FUNCTION: key = argument supplied by the caller.
    # Set key: represent a hash as printable hexadecimal text; this does not reveal its original
    # secret.
    key = hashlib.sha256(key.encode()).hexdigest()
    # owner holds a random identifier that distinguishes our refresh lease from another worker
    # lease. Next, generate a new random UUID for this record or temporary ownership identifier.
    owner = uuid.uuid4()
    # acquired holds whether this refresh worker successfully owns the temporary shared lease.
    # Next, use the boolean False.
    acquired = False
    # Repeat the following block for each _ from range(10). Each iteration handles that one
    # item/pair.
    for _ in range(10):
        # Start an atomic write boundary. Leaving normally commits it; an exception rolls back
        # this block changes.
        with transaction.atomic():
            # Delete the selected row(s), applying their configured related-row deletion rules.
            CacheLease.objects.filter(key=key, expires_at__lt=timezone.now()).delete()
            # Attempt this block; the following except branches handle expected failures without
            # continuing the success path.
            try:
                # Start an atomic write boundary. Leaving normally commits it; an exception rolls
                # back this block changes.
                with transaction.atomic():
                    # Insert a new row and receive the created model object.
                    CacheLease.objects.create(
                        key=key, owner=owner, expires_at=timezone.now() + timedelta(seconds=20)
                    )
                # acquired holds whether this refresh worker successfully owns the temporary
                # shared lease. Next, use the boolean True.
                acquired = True
            # Handle IntegrityError here. The original exception is not automatically safe to
            # expose to the client.
            except IntegrityError:
                # Intentionally do nothing in this branch; the surrounding function continues
                # afterward.
                pass
        # Enter this branch only when acquired. Otherwise execution uses its alternative or
        # continues below.
        if acquired:
            # Leave this loop now; no further source pages/items are attempted by this loop.
            break
        # Call time.sleep with the inputs shown; its definition explains the checks, side effects
        # and return value.
        time.sleep(0.05)
    # Enter this branch only when not acquired. Otherwise execution uses its alternative or
    # continues below.
    if not acquired:
        # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
        # handler builds its JSON envelope.
        raise APIError(
            "service_unavailable",
            "Metadata refresh in progress; retry shortly.",
            503,
            retry_after=1,
        )
    # Attempt this block; the following except branches handle expected failures without
    # continuing the success path.
    try:
        # Evaluate (yield).
        yield
    finally:
        # Delete the selected row(s), applying their configured related-row deletion rules.
        CacheLease.objects.filter(key=key, owner=owner).delete()
